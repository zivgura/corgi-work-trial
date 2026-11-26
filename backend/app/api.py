from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pricing
from . import services as svc
from .config import get_settings
from .db import get_db
from .models import Customer, EmailLog, Payment, Policy, User, WebhookEvent
from .providers import get_payment_provider
from .security import create_token, decode_token, verify_password

router = APIRouter(prefix="/api")


# ---- auth ----------------------------------------------------------------------------------


def current_user(
    authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    try:
        data = decode_token(authorization.split(" ", 1)[1])
    except Exception:
        raise HTTPException(401, "Session expired, please sign in again") from None
    user = db.get(User, int(data["sub"]))
    if not user:
        raise HTTPException(401, "Unknown user")
    return user


def broker_only(user: User = Depends(current_user)) -> User:
    if user.role != "broker":
        raise HTTPException(403, "Brokers only")
    return user


def actor_of(user: User) -> svc.Actor:
    return svc.Actor(user.name, user.role)


def get_policy(db: Session, user: User, policy_id: int) -> Policy:
    p = db.get(Policy, policy_id)
    if not p or (user.role == "customer" and p.customer_id != user.customer_id):
        raise HTTPException(404, "Policy not found")
    return p


class LoginIn(BaseModel):
    email: str
    password: str


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_token(user.id, user.role), "user": _user(user)}


def _user(u: User) -> dict:
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "customer_id": u.customer_id,
    }


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user(user)


@router.get("/config")
def config():
    s = get_settings()
    return {
        "payment_provider": s.payment_provider,
        "stripe_publishable_key": s.stripe_publishable_key
        if s.payment_provider == "stripe"
        else "",
        "email_provider": s.email_provider,
        "catalog": {
            code: {
                "name": c["name"],
                "kind": c["kind"],
                "limits": {k: v for k, v in c["limits"].items()},  # type: ignore[union-attr]
            }
            for code, c in pricing.CATALOG.items()
        },
    }


# ---- customers -----------------------------------------------------------------------------


class CustomerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str = Field(min_length=1, max_length=200)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)


@router.get("/customers")
def list_customers(_: User = Depends(broker_only), db: Session = Depends(get_db)):
    return [
        {"id": c.id, "name": c.name, "contact_name": c.contact_name, "email": c.email}
        for c in db.scalars(select(Customer).order_by(Customer.id.desc()))
    ]


@router.post("/customers")
def create_customer(
    body: CustomerIn, user: User = Depends(broker_only), db: Session = Depends(get_db)
):
    c, u, temp = svc.create_customer(db, actor_of(user), body.name, body.contact_name, body.email)
    db.commit()
    return {
        "customer": {"id": c.id, "name": c.name, "contact_name": c.contact_name, "email": c.email},
        # Sandbox simplification: a real system would send an invite link instead.
        "login": {"email": u.email, "temporary_password": temp},
    }


# ---- policies ------------------------------------------------------------------------------


class CoverageIn(BaseModel):
    code: str
    limit: str


class IssueIn(BaseModel):
    customer_id: int
    start_date: date
    end_date: date
    coverages: list[CoverageIn]


@router.get("/policies")
def list_policies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Policy).order_by(Policy.id.desc())
    if user.role == "customer":
        q = q.where(Policy.customer_id == user.customer_id)
    out = []
    for p in db.scalars(q):
        d = svc.policy_detail(db, p)
        out.append(
            {
                k: d[k]
                for k in (
                    "id",
                    "number",
                    "status",
                    "start_date",
                    "end_date",
                    "balance_cents",
                    "payment_status",
                    "customer",
                )
            }
            | {"coverage_names": [f"{c['name']} {c['limit']}" for c in d["coverages"]]}
        )
    return out


@router.post("/policies")
def issue_policy(body: IssueIn, user: User = Depends(broker_only), db: Session = Depends(get_db)):
    customer = db.get(Customer, body.customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    p = svc.issue_policy(
        db,
        actor_of(user),
        customer,
        body.start_date,
        body.end_date,
        [c.model_dump() for c in body.coverages],
    )
    db.commit()
    return svc.policy_detail(db, p)


@router.get("/policies/{policy_id}")
def get_policy_detail(
    policy_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return svc.policy_detail(db, get_policy(db, user, policy_id))


@router.get("/policies/{policy_id}/statement")
def get_statement(
    policy_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    return svc.statement(db, get_policy(db, user, policy_id))


@router.get("/policies/{policy_id}/timeline")
def get_timeline(policy_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.timeline(db, get_policy(db, user, policy_id))


class AddCoverageIn(BaseModel):
    code: str
    limit: str
    effective_date: date
    reason: str = ""


@router.post("/policies/{policy_id}/coverages")
def add_coverage(
    policy_id: int,
    body: AddCoverageIn,
    user: User = Depends(broker_only),
    db: Session = Depends(get_db),
):
    p = get_policy(db, user, policy_id)
    svc.add_coverage(db, actor_of(user), p, body.code, body.limit, body.effective_date, body.reason)
    db.commit()
    return svc.policy_detail(db, p)


class CorrectIn(BaseModel):
    new_effective_date: date
    reason: str = Field(min_length=1)


@router.post("/policies/{policy_id}/coverages/{coverage_id}/correct-effective-date")
def correct_date(
    policy_id: int,
    coverage_id: int,
    body: CorrectIn,
    user: User = Depends(broker_only),
    db: Session = Depends(get_db),
):
    p = get_policy(db, user, policy_id)
    svc.correct_effective_date(
        db, actor_of(user), p, coverage_id, body.new_effective_date, body.reason
    )
    db.commit()
    return svc.policy_detail(db, p)


class CancelIn(BaseModel):
    cancelled_on: date
    reason: str = ""


@router.post("/policies/{policy_id}/cancel")
def cancel(
    policy_id: int, body: CancelIn, user: User = Depends(broker_only), db: Session = Depends(get_db)
):
    p = get_policy(db, user, policy_id)
    out = svc.cancel_policy(db, actor_of(user), p, body.cancelled_on, body.reason)
    db.commit()
    return {
        "policy": svc.policy_detail(db, p),
        "refunds": [_refund(r) for r in out["refunds"]],
        "refund_error": out["refund_error"],
    }


class RefundIn(BaseModel):
    amount_cents: int | None = Field(default=None, gt=0)


@router.post("/policies/{policy_id}/refund")
def refund(
    policy_id: int, body: RefundIn, user: User = Depends(broker_only), db: Session = Depends(get_db)
):
    p = get_policy(db, user, policy_id)
    rs = svc.issue_refund(db, actor_of(user), p, body.amount_cents)
    db.commit()
    return {"refunds": [_refund(r) for r in rs], "policy": svc.policy_detail(db, p)}


def _refund(r) -> dict:
    return {
        "id": r.id,
        "amount_cents": r.amount_cents,
        "status": r.status,
        "provider_ref": r.provider_ref,
    }


# ---- previews (read-only) ------------------------------------------------------------------


class PreviewIn(BaseModel):
    kind: str  # add_coverage | correction | cancel
    code: str | None = None
    limit: str | None = None
    effective_date: date | None = None
    coverage_id: int | None = None
    new_effective_date: date | None = None
    cancelled_on: date | None = None


@router.post("/policies/{policy_id}/preview")
def preview(
    policy_id: int,
    body: PreviewIn,
    user: User = Depends(broker_only),
    db: Session = Depends(get_db),
):
    p = get_policy(db, user, policy_id)
    if body.kind == "add_coverage" and body.code and body.limit and body.effective_date:
        return svc.simulate(db, p, new_coverage=(body.code, body.limit, body.effective_date))
    if body.kind == "correction" and body.coverage_id and body.new_effective_date:
        return svc.simulate(db, p, override=(body.coverage_id, body.new_effective_date))
    if body.kind == "cancel" and body.cancelled_on:
        return svc.simulate(db, p, cancel_on=body.cancelled_on)
    raise HTTPException(422, "Incomplete preview request")


# ---- payments ------------------------------------------------------------------------------


@router.post("/policies/{policy_id}/payments")
def start_payment(
    policy_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    p = get_policy(db, user, policy_id)
    pay = svc.create_payment(db, actor_of(user), p)
    db.commit()
    return {
        "payment": _payment(pay),
        "client_secret": getattr(pay, "client_secret", None),
        "mode": get_settings().payment_provider,
    }


@router.get("/policies/{policy_id}/payments")
def list_payments(
    policy_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
):
    p = get_policy(db, user, policy_id)
    return [
        _payment(x)
        for x in db.scalars(
            select(Payment).where(Payment.policy_id == p.id).order_by(Payment.id.desc())
        )
    ]


def _payment(p: Payment) -> dict:
    return {
        "id": p.id,
        "policy_id": p.policy_id,
        "provider": p.provider,
        "provider_ref": p.provider_ref,
        "amount_cents": p.amount_cents,
        "status": p.status,
        "failure_reason": p.failure_reason,
        "refunded_cents": p.refunded_cents,
        "created_at": p.created_at.isoformat(),
    }


class SimulateIn(BaseModel):
    outcome: str  # succeed | decline


@router.post("/payments/{payment_id}/simulate")
def simulate_payment(
    payment_id: int,
    body: SimulateIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """SIMULATED mode only: stands in for Stripe's webhook, through the same event handler."""
    pay = db.get(Payment, payment_id)
    if not pay:
        raise HTTPException(404, "Payment not found")
    get_policy(db, user, pay.policy_id)
    if pay.provider != "fake":
        raise HTTPException(400, "Simulation is only available in simulated payment mode")
    ok = body.outcome == "succeed"
    result = svc.apply_provider_event(
        db,
        svc.ProviderEvent(
            id=f"evt_sim_{uuid.uuid4().hex[:12]}",
            type="payment_succeeded" if ok else "payment_failed",
            ref=pay.provider_ref,
            failure_reason=None
            if ok
            else "Your card was declined (simulated test card ending 0002).",
            provider="fake",
        ),
    )
    db.commit()
    db.refresh(pay)
    return {"result": result, "payment": _payment(pay)}


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    payload = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            payload, request.headers.get("stripe-signature", ""), s.stripe_webhook_secret
        )
    except Exception as exc:
        raise HTTPException(400, f"Invalid webhook: {exc}") from None
    obj = event["data"]["object"]
    t = event["type"]
    ev = None
    if t == "payment_intent.succeeded":
        ev = svc.ProviderEvent(
            event["id"], "payment_succeeded", obj["id"], provider="stripe", raw=dict(event)
        )
    elif t == "payment_intent.payment_failed":
        msg = (obj.get("last_payment_error") or {}).get("message", "Payment failed")
        ev = svc.ProviderEvent(event["id"], "payment_failed", obj["id"], msg, "stripe", dict(event))
    elif t in ("charge.refunded", "refund.created", "refund.updated"):
        ev = svc.ProviderEvent(
            event["id"],
            "refund_succeeded",
            obj.get("payment_intent") or obj["id"],
            provider="stripe",
            raw=dict(event),
        )
    if ev is None:
        return {"received": True, "handled": False}
    result = svc.apply_provider_event(db, ev)
    db.commit()
    return {"received": True, "handled": True, "result": result}


# ---- ops / evidence (broker) ---------------------------------------------------------------


@router.get("/ops/events")
def ops_events(_: User = Depends(broker_only), db: Session = Depends(get_db)):
    ev = db.scalars(select(WebhookEvent).order_by(WebhookEvent.received_at.desc()).limit(100))
    mail = db.scalars(select(EmailLog).order_by(EmailLog.id.desc()).limit(100))
    return {
        "payment_provider": get_payment_provider().name,
        "provider_events": [
            {
                "id": e.id,
                "provider": e.provider,
                "type": e.type,
                "received_at": e.received_at.isoformat(),
            }
            for e in ev
        ],
        "emails": [
            {
                "id": m.id,
                "policy_id": m.policy_id,
                "to": m.to,
                "subject": m.subject,
                "template": m.template,
                "provider": m.provider,
                "status": m.status,
                "provider_id": m.provider_id,
                "error": m.error,
                "created_at": m.created_at.isoformat(),
                "body": m.body,
            }
            for m in mail
        ],
    }


# ---- demo helper ---------------------------------------------------------------------------


class ScenarioIn(BaseModel):
    customer_id: int


@router.post("/demo/scenario")
def demo_scenario(
    body: ScenarioIn, user: User = Depends(broker_only), db: Session = Depends(get_db)
):
    """Creates a policy whose premium and mid-term coverage change are already paid, so the
    effective-date correction can be tried straight away. Payments here are SIMULATED."""
    from .seed import load_scenario

    customer = db.get(Customer, body.customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    if get_settings().payment_provider != "fake":
        raise HTTPException(
            400, "Scenario loader uses simulated payments; unavailable with Stripe mode"
        )
    p = load_scenario(db, actor_of(user), customer)
    return svc.policy_detail(db, p)
