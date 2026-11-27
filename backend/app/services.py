"""Business logic. Every money-moving action goes through here and produces ledger entries
that point back at an `Action` row, so any amount can be traced to what caused it."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import pricing
from .config import get_settings
from .email_html import html_with_note, render_email_html
from .models import (
    Action,
    Coverage,
    CoverageVersion,
    Customer,
    EmailLog,
    LedgerEntry,
    Payment,
    Policy,
    Refund,
    User,
    WebhookEvent,
)
from .pricing import format_usd as usd
from .providers import ProviderError, get_email_provider, get_payment_provider
from .security import hash_password

PREMIUM_TYPES = ("CHARGE", "ADJUSTMENT", "CREDIT")


class DomainError(Exception):
    """A rule was violated; message is safe to show to the user."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class Actor:
    name: str
    role: str  # broker | customer | system


SYSTEM = Actor("System", "system")


def fmt_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


# ---- ledger primitives --------------------------------------------------------------------


def balance(db: Session, policy_id: int) -> int:
    db.flush()
    return int(
        db.scalar(
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                LedgerEntry.policy_id == policy_id
            )
        )
        or 0
    )


def _action(
    db: Session,
    policy: Policy,
    kind: str,
    actor: Actor,
    summary: str,
    note: str = "",
    payload: dict[str, Any] | None = None,
) -> Action:
    a = Action(
        policy_id=policy.id,
        kind=kind,
        actor=actor.name,
        summary=summary,
        note=note,
        payload=payload or {},
    )
    db.add(a)
    db.flush()
    return a


def _entry(
    db: Session,
    policy: Policy,
    action: Action,
    type_: str,
    amount: int,
    description: str,
    calc: dict[str, Any] | None = None,
    coverage: Coverage | None = None,
    payment: Payment | None = None,
    refund: Refund | None = None,
) -> LedgerEntry:
    e = LedgerEntry(
        policy_id=policy.id,
        action_id=action.id,
        type=type_,
        amount_cents=amount,
        coverage_id=coverage.id if coverage else None,
        payment_id=payment.id if payment else None,
        refund_id=refund.id if refund else None,
        description=description,
        calc=calc or {},
    )
    db.add(e)
    db.flush()
    return e


def reconcile(
    db: Session, policy: Policy, action: Action, extra: dict[str, Any] | None = None
) -> list[LedgerEntry]:
    """Make the ledger agree with the policy as it is *now*.

    For each coverage: expected premium = pro-rata from its CURRENT effective date to the end
    of the term (or the cancellation date). booked = what the ledger already holds for that
    coverage. Any difference is appended as a new entry; existing entries are never touched.
    That is what keeps "original charge" and "correction" both visible.
    """
    db.flush()
    created: list[LedgerEntry] = []
    for cov in policy.coverages:
        cur = cov.current
        pr = pricing.prorate(
            cov.term_premium_cents,
            policy.start_date,
            policy.end_date,
            cur.effective_date,
            policy.cancelled_on,
        )
        booked, n_entries = db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0), func.count()).where(
                LedgerEntry.coverage_id == cov.id, LedgerEntry.type.in_(PREMIUM_TYPES)
            )
        ).one()
        booked = int(booked)
        delta = pr.amount_cents - booked
        if delta == 0:
            continue
        if n_entries == 0:
            type_ = "CHARGE"
        elif action.kind == "CANCEL_POLICY":
            type_ = "CREDIT"
        else:
            type_ = "ADJUSTMENT"
        calc = {
            **pr.as_dict(),
            "previously_booked_cents": booked,
            "delta_cents": delta,
            "coverage_name": f"{cov.name} {cov.limit}",
            **(extra or {}),
        }
        if extra and extra.get("coverage_id") not in (None, cov.id):
            # `extra` describes one coverage only; don't leak it onto the others
            calc = {k: v for k, v in calc.items() if k not in extra}
            calc.update({"coverage_name": f"{cov.name} {cov.limit}"})
        desc = _describe(type_, cov, delta, action, calc)
        created.append(_entry(db, policy, action, type_, delta, desc, calc, coverage=cov))
    return created


def _describe(type_: str, cov: Coverage, delta: int, action: Action, calc: dict) -> str:
    name = f"{cov.name} {cov.limit}"
    if type_ == "CHARGE":
        return f"Premium: {name}"
    if type_ == "CREDIT":
        return f"Cancellation credit: {name}"
    if calc.get("previous_effective_date") and calc.get("new_effective_date"):
        return (
            f"Correction: {name} start date "
            f"{_d(calc['previous_effective_date'])} → {_d(calc['new_effective_date'])}"
        )
    return f"Adjustment: {name}"


def explain(entry: LedgerEntry) -> str:
    """Human-readable derivation of a ledger line (what the debrief will ask for)."""
    c = entry.calc or {}
    if entry.type in PREMIUM_TYPES and "term_days" in c:
        span = (
            f"{c['covered_days']}/{c['term_days']} days "
            f"({_d(c['effective_date'])} → {_d(c['end_date'])})"
        )
        earned = f"{usd(c['term_premium_cents'])} term premium × {span} = {usd(c['amount_cents'])}"
        if entry.type == "CHARGE":
            if c["covered_days"] == c["term_days"]:
                return f"Full-term premium {usd(c['amount_cents'])} (all {c['term_days']} days)."
            return f"{earned}."
        if entry.type == "ADJUSTMENT":
            head = ""
            if c.get("previous_effective_date") and c.get("new_effective_date"):
                head = (
                    f"Effective date corrected {_d(c['previous_effective_date'])} → "
                    f"{_d(c['new_effective_date'])}. "
                )
            return (
                f"{head}Now earned: {earned}. Previously charged "
                f"{usd(c['previously_booked_cents'])}. Difference "
                f"{'+' if c['delta_cents'] >= 0 else '−'}{usd(abs(c['delta_cents']))}."
            )
        if entry.type == "CREDIT":
            return (
                f"Cancelled effective {_d(c['end_date'])}. Earned: {earned}. Previously charged "
                f"{usd(c['previously_booked_cents'])}. Unearned {usd(abs(c['delta_cents']))} "
                f"credited."
            )
    if entry.type == "PAYMENT":
        return f"Payment of {usd(abs(entry.amount_cents))} received ({c.get('provider_ref', '')})."
    if entry.type == "REFUND":
        return f"Refund of {usd(entry.amount_cents)} sent to the original payment method."
    return entry.description


def _d(iso: str) -> str:
    y, m, d = (int(x) for x in iso.split("-"))
    return fmt_date(date(y, m, d))


# ---- email --------------------------------------------------------------------------------


def notify(db: Session, policy: Policy | None, to: str, template: str, subject: str, body: str):
    prov = get_email_provider()
    portal = get_settings().app_url.rstrip("/") + (
        f"/portal/policies/{policy.id}" if policy else "/portal"
    )
    html = render_email_html(template, subject, body, portal)
    redirect = get_settings().email_redirect_to.strip()
    if redirect and redirect.lower() != to.lower():
        note = (
            f"Demo sandbox: this email is addressed to {to}. Resend's test sender can only "
            "deliver to the account owner, so it was redirected here."
        )
        res = prov.send(
            redirect, f"[to {to}] {subject}", f"{note}\n\n{body}", html_with_note(html, note)
        )
    else:
        res = prov.send(to, subject, body, html)
    db.add(
        EmailLog(
            policy_id=policy.id if policy else None,
            to=to,
            subject=subject,
            body=body,
            template=template,
            provider=prov.name,
            status=res.status,
            provider_id=res.provider_id,
            error=res.error,
        )
    )
    db.flush()


# ---- customers ----------------------------------------------------------------------------


def create_customer(
    db: Session, actor: Actor, name: str, contact_name: str, email: str
) -> tuple[Customer, User, str]:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise DomainError("A user with that email already exists")
    c = Customer(name=name.strip(), contact_name=contact_name.strip(), email=email)
    db.add(c)
    db.flush()
    temp = secrets.token_urlsafe(8)
    u = User(
        email=email,
        name=contact_name.strip(),
        password_hash=hash_password(temp),
        role="customer",
        customer_id=c.id,
    )
    db.add(u)
    db.flush()
    return c, u, temp


# ---- policy lifecycle ---------------------------------------------------------------------


def _next_number(db: Session) -> str:
    n = (db.scalar(select(func.count()).select_from(Policy)) or 0) + 1
    return f"CRG-{n:06d}"


def _require_active(policy: Policy) -> None:
    if policy.status != "active":
        raise DomainError("This policy is cancelled and can no longer be changed that way")


def issue_policy(
    db: Session,
    actor: Actor,
    customer: Customer,
    start: date,
    end: date,
    items: list[dict[str, str]],
) -> Policy:
    if not items:
        raise DomainError("Choose at least one coverage")
    try:
        pricing.term_days(start, end)
    except pricing.PricingError as exc:
        raise DomainError(str(exc)) from exc
    if len({i["code"] for i in items}) != len(items):
        raise DomainError("Each coverage can only be added once")

    policy = Policy(
        number=_next_number(db), customer_id=customer.id, start_date=start, end_date=end
    )
    db.add(policy)
    db.flush()
    action = _action(
        db,
        policy,
        "ISSUE_POLICY",
        actor,
        f"Policy issued ({fmt_date(start)} → {fmt_date(end)})",
        payload={"start": start.isoformat(), "end": end.isoformat(), "items": items},
    )
    for it in items:
        _new_coverage(db, policy, actor, action, it["code"], it["limit"], start, "Policy issued")
    db.flush()
    db.refresh(policy)
    reconcile(db, policy, action)
    due = balance(db, policy.id)
    notify(
        db,
        policy,
        customer.email,
        "policy_issued",
        f"Your Corgi policy {policy.number} is ready",
        f"Hi {customer.contact_name},\n\nPolicy {policy.number} for {customer.name} is issued, "
        f"covering {fmt_date(start)} to {fmt_date(end)} (expires {fmt_date(end)}).\n"
        f"Premium due: {usd(due)}. Log in to your portal to pay.\n\n— Corgi (demo)",
    )
    return policy


def _new_coverage(
    db: Session,
    policy: Policy,
    actor: Actor,
    action: Action,
    code: str,
    limit: str,
    effective: date,
    reason: str,
) -> Coverage:
    try:
        tp = pricing.term_premium(code, limit, policy.start_date, policy.end_date)
        info = pricing.CATALOG[code]
        if effective < policy.start_date or effective >= policy.end_date:
            raise pricing.PricingError("Effective date must fall within the policy term")
    except pricing.PricingError as exc:
        raise DomainError(str(exc)) from exc
    cov = Coverage(
        policy_id=policy.id,
        code=code,
        name=str(info["name"]),
        limit=limit,
        kind=str(info["kind"]),
        term_premium_cents=tp,
    )
    db.add(cov)
    db.flush()
    db.add(
        CoverageVersion(
            coverage_id=cov.id,
            effective_date=effective,
            recorded_by=actor.name,
            reason=reason,
            action_id=action.id,
            is_current=True,
        )
    )
    db.flush()
    db.refresh(cov)
    return cov


def add_coverage(
    db: Session,
    actor: Actor,
    policy: Policy,
    code: str,
    limit: str,
    effective: date,
    reason: str = "",
) -> Policy:
    _require_active(policy)
    if any(c.code == code for c in policy.coverages):
        raise DomainError("That coverage is already on the policy")
    name = f"{pricing.CATALOG.get(code, {}).get('name', code)} {limit}"
    action = _action(
        db,
        policy,
        "ADD_COVERAGE",
        actor,
        f"Added {name} effective {fmt_date(effective)}",
        note=reason,
        payload={"code": code, "limit": limit, "effective_date": effective.isoformat()},
    )
    cov = _new_coverage(db, policy, actor, action, code, limit, effective, reason or "Added")
    db.refresh(policy)
    entries = reconcile(db, policy, action, extra={"coverage_id": cov.id})
    amt = sum(e.amount_cents for e in entries)
    notify(
        db,
        policy,
        policy.customer.email,
        "coverage_added",
        f"Coverage added to {policy.number}",
        f"{name} now applies from {fmt_date(effective)}. Additional premium {usd(amt)}. "
        f"Amount due: {usd(balance(db, policy.id))}.\n\n— Corgi (demo)",
    )
    return policy


def correct_effective_date(
    db: Session,
    actor: Actor,
    policy: Policy,
    coverage_id: int,
    new_date: date,
    reason: str,
) -> Policy:
    if not reason or not reason.strip():
        raise DomainError("A reason is required for a correction")
    cov = next((c for c in policy.coverages if c.id == coverage_id), None)
    if cov is None:
        raise DomainError("Coverage not found on this policy", 404)
    old = cov.current
    if new_date == old.effective_date:
        raise DomainError("The new effective date is the same as the current one")
    if new_date < policy.start_date or new_date >= policy.end_date:
        raise DomainError("Effective date must fall within the policy term")
    if policy.cancelled_on and new_date >= policy.cancelled_on:
        raise DomainError("Effective date must be before the cancellation date")

    name = f"{cov.name} {cov.limit}"
    action = _action(
        db,
        policy,
        "CORRECT_EFFECTIVE_DATE",
        actor,
        f"Corrected {name} effective date {fmt_date(old.effective_date)} → {fmt_date(new_date)}",
        note=reason.strip(),
        payload={
            "coverage_id": cov.id,
            "previous_effective_date": old.effective_date.isoformat(),
            "new_effective_date": new_date.isoformat(),
        },
    )
    old.is_current = False
    db.add(
        CoverageVersion(
            coverage_id=cov.id,
            effective_date=new_date,
            recorded_by=actor.name,
            reason=reason.strip(),
            action_id=action.id,
            is_current=True,
        )
    )
    db.flush()
    db.refresh(cov)
    entries = reconcile(
        db,
        policy,
        action,
        extra={
            "coverage_id": cov.id,
            "previous_effective_date": old.effective_date.isoformat(),
            "new_effective_date": new_date.isoformat(),
        },
    )
    delta = sum(e.amount_cents for e in entries)
    due = balance(db, policy.id)
    if due > 0:
        tail = f"Amount now due: {usd(due)}."
    elif due < 0:
        tail = f"You have a credit of {usd(-due)} on this policy."
    else:
        tail = "Nothing further is due."
    notify(
        db,
        policy,
        policy.customer.email,
        "coverage_corrected",
        f"Correction to {policy.number}",
        f"We corrected when {name} began: {fmt_date(old.effective_date)} → "
        f"{fmt_date(new_date)} ({reason.strip()}). Premium change: "
        f"{'+' if delta >= 0 else '−'}{usd(abs(delta))}. Your original charge is unchanged on "
        f"your statement; the correction is a separate line. {tail}\n\n— Corgi (demo)",
    )
    return policy


def cancel_policy(
    db: Session, actor: Actor, policy: Policy, cancelled_on: date, reason: str = ""
) -> dict[str, Any]:
    _require_active(policy)
    if cancelled_on < policy.start_date or cancelled_on >= policy.end_date:
        raise DomainError("Cancellation date must fall within the policy term")
    action = _action(
        db,
        policy,
        "CANCEL_POLICY",
        actor,
        f"Policy cancelled effective {fmt_date(cancelled_on)}",
        note=reason,
        payload={"cancelled_on": cancelled_on.isoformat()},
    )
    policy.status = "cancelled"
    policy.cancelled_on = cancelled_on
    policy.cancel_reason = reason
    db.flush()
    entries = reconcile(db, policy, action)
    credit = sum(e.amount_cents for e in entries)
    refunds: list[Refund] = []
    refund_error = None
    if balance(db, policy.id) < 0:
        try:
            refunds = issue_refund(db, actor, policy, reason="Cancellation refund")
        except DomainError as exc:
            refund_error = exc.message
    due = balance(db, policy.id)
    notify(
        db,
        policy,
        policy.customer.email,
        "policy_cancelled",
        f"Policy {policy.number} cancelled",
        f"Your policy was cancelled effective {fmt_date(cancelled_on)}. Premium change: "
        f"{usd(credit)}. Refunded: {usd(sum(r.amount_cents for r in refunds if r.status == 'succeeded'))}."
        f" Balance: {usd(due)}.\n\n— Corgi (demo)",
    )
    return {"policy": policy, "refunds": refunds, "refund_error": refund_error}


# ---- payments & refunds -------------------------------------------------------------------


def sync_pending_payments(db: Session, policy: Policy) -> bool:
    """Reconcile open payment attempts with the provider. The signed webhook is the normal path; this
    is the safety net for a webhook that is late, lost or rejected, so a paid policy never looks unpaid
    and a customer is never offered the same payment twice. Goes through the same idempotent handler,
    so a webhook arriving afterwards changes nothing."""
    provider = get_payment_provider()
    changed = False
    pending = db.scalars(
        select(Payment).where(
            Payment.policy_id == policy.id,
            Payment.status == "pending",
            Payment.provider == provider.name,
        )
    ).all()
    for p in pending:
        try:
            st = provider.payment_state(p.provider_ref)
        except ProviderError:
            continue  # best effort: the webhook remains the source of truth
        if st.state == "succeeded":
            ev = ProviderEvent(
                f"sync_{p.provider_ref}_succeeded",
                "payment_succeeded",
                p.provider_ref,
                provider=provider.name,
                raw={"ref": p.provider_ref, "source": "reconciliation"},
            )
            changed |= apply_provider_event(db, ev) == "applied"
        elif st.state == "failed":
            ev = ProviderEvent(
                f"sync_{p.provider_ref}_failed",
                "payment_failed",
                p.provider_ref,
                st.failure_reason,
                provider=provider.name,
                raw={"ref": p.provider_ref, "source": "reconciliation"},
            )
            changed |= apply_provider_event(db, ev) == "applied"
        elif st.state == "canceled":
            p.status = "canceled"
            changed = True
    return changed


def create_payment(db: Session, actor: Actor, policy: Policy) -> Payment:
    sync_pending_payments(
        db, policy
    )  # a payment that already went through must not be offered again
    due = balance(db, policy.id)
    if due <= 0:
        raise DomainError("Nothing is due on this policy")
    pending = db.scalars(
        select(Payment).where(Payment.policy_id == policy.id, Payment.status == "pending")
    ).all()
    provider = get_payment_provider()
    for p in pending:
        if p.amount_cents == due and p.provider == provider.name:
            # Idempotent: reuse the open attempt. The client secret is never stored, so fetch it
            # again; without it the customer's browser cannot render the card form.
            try:
                p.client_secret = provider.client_secret_for(p.provider_ref)  # type: ignore[attr-defined]
            except ProviderError as exc:
                raise DomainError(f"Payment provider error: {exc}", 502) from exc
            return p
        p.status = "canceled"  # amount changed, or created under a different provider mode
    try:
        res = provider.create_payment(
            due,
            f"Corgi policy {policy.number}",
            {"policy_id": str(policy.id), "policy_number": policy.number},
        )
    except ProviderError as exc:
        raise DomainError(f"Payment provider error: {exc}", 502) from exc
    pay = Payment(
        policy_id=policy.id,
        provider=provider.name,
        provider_ref=res.ref,
        amount_cents=due,
        status="pending",
        created_by=actor.name,
    )
    db.add(pay)
    db.flush()
    pay.client_secret = res.client_secret  # type: ignore[attr-defined]  # transient, not stored
    _action(
        db,
        policy,
        "PAYMENT_STARTED",
        actor,
        f"Payment of {usd(due)} started ({provider.name})",
        payload={"payment_id": pay.id, "provider_ref": pay.provider_ref},
    )
    return pay


@dataclass
class ProviderEvent:
    id: str
    type: str  # payment_succeeded | payment_failed | refund_succeeded
    ref: str
    failure_reason: str | None = None
    provider: str = "stripe"
    raw: dict[str, Any] | None = None


def _claim_payment(
    db: Session, pay: Payment, *, to: str, unless: tuple[str, ...], reason: str | None = None
) -> bool:
    """Move a payment to `to` only if it is not already in a state listed in `unless`.
    One SQL statement, so exactly one concurrent caller gets True."""
    res = db.execute(
        update(Payment)
        .where(Payment.id == pay.id, Payment.status.notin_(unless))
        .values(status=to, failure_reason=reason)
        .execution_options(synchronize_session=False)
    )
    if res.rowcount != 1:  # type: ignore[attr-defined]
        return False
    db.refresh(pay)
    return True


def apply_provider_event(db: Session, ev: ProviderEvent) -> str:
    """Single entry point for Stripe webhooks AND simulated confirmations. Idempotent."""
    if db.get(WebhookEvent, ev.id):
        return "duplicate"
    db.add(
        WebhookEvent(
            id=ev.id, provider=ev.provider, type=ev.type, payload=ev.raw or {"ref": ev.ref}
        )
    )
    db.flush()
    if ev.type == "refund_succeeded":
        return "recorded"  # refunds are booked when we create them; event kept as evidence
    pay = db.scalar(select(Payment).where(Payment.provider_ref == ev.ref))
    if pay is None:
        return "ignored"
    policy = db.get(Policy, pay.policy_id)
    assert policy is not None
    if ev.type == "payment_succeeded":
        # Atomic compare-and-set: the webhook request and a polled reconciliation can run in
        # different threads/transactions and both read "pending". Only the caller whose UPDATE
        # actually changes the row may book the ledger entry and send the email.
        if not _claim_payment(db, pay, to="succeeded", unless=("succeeded",)):
            return "duplicate"
        action = _action(
            db,
            policy,
            "PAYMENT_SUCCEEDED",
            SYSTEM,
            f"Payment of {usd(pay.amount_cents)} succeeded",
            payload={"payment_id": pay.id, "provider_ref": pay.provider_ref, "event": ev.id},
        )
        _entry(
            db,
            policy,
            action,
            "PAYMENT",
            -pay.amount_cents,
            "Payment received",
            {"provider_ref": pay.provider_ref, "provider": pay.provider},
            payment=pay,
        )
        notify(
            db,
            policy,
            policy.customer.email,
            "payment_received",
            f"Payment received for {policy.number}",
            f"We received {usd(pay.amount_cents)}. Balance: {usd(balance(db, policy.id))}.\n\n"
            "— Corgi (demo)",
        )
        return "applied"
    if ev.type == "payment_failed":
        if pay.status == "succeeded":
            return "ignored"
        if not _claim_payment(
            db,
            pay,
            to="failed",
            unless=("succeeded", "failed"),
            reason=ev.failure_reason or "Payment failed",
        ):
            return "duplicate"
        _action(
            db,
            policy,
            "PAYMENT_FAILED",
            SYSTEM,
            f"Payment of {usd(pay.amount_cents)} failed: {pay.failure_reason}",
            payload={"payment_id": pay.id, "provider_ref": pay.provider_ref, "event": ev.id},
        )
        notify(
            db,
            policy,
            policy.customer.email,
            "payment_failed",
            f"Payment failed for {policy.number}",
            f"Your payment of {usd(pay.amount_cents)} didn't go through "
            f"({pay.failure_reason}). You can try again from your portal.\n\n— Corgi (demo)",
        )
        return "applied"
    return "ignored"


def issue_refund(
    db: Session,
    actor: Actor,
    policy: Policy,
    amount_cents: int | None = None,
    reason: str = "Refund of credit on account",
) -> list[Refund]:
    """Refund customer credit (a negative balance) to the original payment method(s)."""
    bal = balance(db, policy.id)
    if bal >= 0:
        raise DomainError("There is no credit on this policy to refund")
    credit = -bal
    payments = db.scalars(
        select(Payment)
        .where(Payment.policy_id == policy.id, Payment.status == "succeeded")
        .order_by(Payment.id.desc())
    ).all()
    refundable = sum(p.amount_cents - p.refunded_cents for p in payments)
    if refundable <= 0:
        raise DomainError("No successful payments left to refund against")
    amt = min(credit, refundable) if amount_cents is None else amount_cents
    if amt <= 0 or amt > credit or amt > refundable:
        raise DomainError(
            f"Refund must be between $0.01 and {usd(min(credit, refundable))} "
            f"(credit {usd(credit)}, refundable {usd(refundable)})"
        )
    action = _action(
        db,
        policy,
        "REFUND_ISSUED",
        actor,
        f"Refund of {usd(amt)} issued",
        note=reason,
        payload={"amount_cents": amt},
    )
    provider = get_payment_provider()
    out: list[Refund] = []
    remaining = amt
    for pay in payments:
        if remaining <= 0:
            break
        take = min(remaining, pay.amount_cents - pay.refunded_cents)
        if take <= 0:
            continue
        r = Refund(policy_id=policy.id, payment_id=pay.id, amount_cents=take, status="pending")
        db.add(r)
        db.flush()
        try:
            r.provider_ref = provider.refund(
                pay.provider_ref, take, f"refund-{pay.provider_ref}-{r.id}"
            )
            r.status = "succeeded"
            pay.refunded_cents += take
            _entry(
                db,
                policy,
                action,
                "REFUND",
                take,
                "Refund to original payment method",
                {"provider_ref": r.provider_ref, "payment_ref": pay.provider_ref},
                payment=pay,
                refund=r,
            )
            remaining -= take
        except ProviderError as exc:
            r.status = "failed"
            r.failure_reason = str(exc)
        out.append(r)
    ok = sum(r.amount_cents for r in out if r.status == "succeeded")
    if ok == 0:
        raise DomainError("The payment provider rejected the refund", 502)
    notify(
        db,
        policy,
        policy.customer.email,
        "refund_issued",
        f"Refund issued for {policy.number}",
        f"We refunded {usd(ok)} to your original payment method. It can take a few days to "
        f"appear. Balance: {usd(balance(db, policy.id))}.\n\n— Corgi (demo)",
    )
    return out


# ---- read models --------------------------------------------------------------------------


def statement(db: Session, policy: Policy) -> dict[str, Any]:
    db.flush()
    entries = db.scalars(
        select(LedgerEntry).where(LedgerEntry.policy_id == policy.id).order_by(LedgerEntry.id)
    ).all()
    rows, running = [], 0
    for e in entries:
        running += e.amount_cents
        rows.append(
            {
                "id": e.id,
                "date": e.created_at.isoformat(),
                "type": e.type,
                "description": e.description,
                "amount_cents": e.amount_cents,
                "running_balance_cents": running,
                "explanation": explain(e),
                "calc": e.calc,
                "coverage_id": e.coverage_id,
                "payment_id": e.payment_id,
                "refund_id": e.refund_id,
                "action": {
                    "id": e.action.id,
                    "kind": e.action.kind,
                    "summary": e.action.summary,
                    "actor": e.action.actor,
                    "note": e.action.note,
                    "at": e.action.created_at.isoformat(),
                },
            }
        )
    attempts = db.scalars(
        select(Payment)
        .where(Payment.policy_id == policy.id, Payment.status != "succeeded")
        .order_by(Payment.id)
    ).all()
    charged = sum(e.amount_cents for e in entries if e.type in PREMIUM_TYPES)
    paid = -sum(e.amount_cents for e in entries if e.type == "PAYMENT")
    refunded = sum(e.amount_cents for e in entries if e.type == "REFUND")
    return {
        "policy_id": policy.id,
        "policy_number": policy.number,
        "rows": rows,
        "balance_cents": running,
        "totals": {
            "net_premium_cents": charged,
            "paid_cents": paid,
            "refunded_cents": refunded,
        },
        "payment_attempts": [
            {
                "id": p.id,
                "status": p.status,
                "amount_cents": p.amount_cents,
                "failure_reason": p.failure_reason,
                "provider": p.provider,
                "created_at": p.created_at.isoformat(),
            }
            for p in attempts
        ],
    }


def timeline(db: Session, policy: Policy) -> list[dict[str, Any]]:
    acts = db.scalars(select(Action).where(Action.policy_id == policy.id).order_by(Action.id)).all()
    return [
        {
            "id": a.id,
            "kind": a.kind,
            "summary": a.summary,
            "actor": a.actor,
            "note": a.note,
            "at": a.created_at.isoformat(),
            "payload": a.payload,
        }
        for a in acts
    ]


def policy_detail(db: Session, policy: Policy) -> dict[str, Any]:
    bal = balance(db, policy.id)
    pending = db.scalar(
        select(Payment).where(Payment.policy_id == policy.id, Payment.status == "pending")
    )
    covs = []
    for c in policy.coverages:
        cur = c.current
        pr = pricing.prorate(
            c.term_premium_cents,
            policy.start_date,
            policy.end_date,
            cur.effective_date,
            policy.cancelled_on,
        )
        covs.append(
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "limit": c.limit,
                "kind": c.kind,
                "term_premium_cents": c.term_premium_cents,
                "effective_date": cur.effective_date.isoformat(),
                "earned_premium_cents": pr.amount_cents,
                "covered_days": pr.covered_days,
                "versions": [
                    {
                        "id": v.id,
                        "effective_date": v.effective_date.isoformat(),
                        "recorded_at": v.recorded_at.isoformat(),
                        "recorded_by": v.recorded_by,
                        "reason": v.reason,
                        "is_current": v.is_current,
                    }
                    for v in c.versions
                ],
            }
        )
    return {
        "id": policy.id,
        "number": policy.number,
        "status": policy.status,
        "start_date": policy.start_date.isoformat(),
        "end_date": policy.end_date.isoformat(),
        "term_days": pricing.term_days(policy.start_date, policy.end_date),
        "cancelled_on": policy.cancelled_on.isoformat() if policy.cancelled_on else None,
        "cancel_reason": policy.cancel_reason,
        "customer": {
            "id": policy.customer.id,
            "name": policy.customer.name,
            "contact_name": policy.customer.contact_name,
            "email": policy.customer.email,
        },
        "coverages": covs,
        "balance_cents": bal,
        "payment_status": ("pending" if pending else _last_payment_status(db, policy.id)),
    }


def _last_payment_status(db: Session, policy_id: int) -> str | None:
    p = db.scalar(select(Payment).where(Payment.policy_id == policy_id).order_by(Payment.id.desc()))
    return p.status if p else None


# ---- what-if previews (no writes) ----------------------------------------------------------


def simulate(
    db: Session,
    policy: Policy,
    *,
    new_coverage: tuple[str, str, date] | None = None,
    override: tuple[int, date] | None = None,
    cancel_on: date | None = None,
) -> dict[str, Any]:
    """Compute what reconcile() WOULD append, without writing anything. Used by the broker UI
    so the amount is visible before the action is confirmed."""
    db.flush()
    cancelled = cancel_on or policy.cancelled_on
    lines: list[dict[str, Any]] = []
    try:
        for cov in policy.coverages:
            eff = cov.current.effective_date
            if override and override[0] == cov.id:
                eff = override[1]
            if cancelled and eff >= cancelled:
                # coverage would start on/after cancellation: earns nothing
                pr = pricing.prorate(
                    cov.term_premium_cents,
                    policy.start_date,
                    policy.end_date,
                    policy.start_date,
                    policy.start_date,
                )
            else:
                pr = pricing.prorate(
                    cov.term_premium_cents, policy.start_date, policy.end_date, eff, cancelled
                )
            booked = int(
                db.scalar(
                    select(func.coalesce(func.sum(LedgerEntry.amount_cents), 0)).where(
                        LedgerEntry.coverage_id == cov.id, LedgerEntry.type.in_(PREMIUM_TYPES)
                    )
                )
                or 0
            )
            lines.append(_sim_line(f"{cov.name} {cov.limit}", eff, pr, booked))
        if new_coverage:
            code, limit, eff = new_coverage
            tp = pricing.term_premium(code, limit, policy.start_date, policy.end_date)
            pr = pricing.prorate(tp, policy.start_date, policy.end_date, eff, cancelled)
            lines.append(_sim_line(f"{pricing.CATALOG[code]['name']} {limit}", eff, pr, 0))
    except pricing.PricingError as exc:
        raise DomainError(str(exc)) from exc
    delta = sum(line["delta_cents"] for line in lines)
    current = balance(db, policy.id)
    paid_refundable = sum(
        p.amount_cents - p.refunded_cents
        for p in db.scalars(
            select(Payment).where(Payment.policy_id == policy.id, Payment.status == "succeeded")
        )
    )
    new_balance = current + delta
    return {
        "lines": lines,
        "premium_change_cents": delta,
        "current_balance_cents": current,
        "new_balance_cents": new_balance,
        "refund_cents": (
            min(-new_balance, paid_refundable) if cancel_on and new_balance < 0 else 0
        ),
    }


def _sim_line(name: str, eff: date, pr: pricing.Proration, booked: int) -> dict[str, Any]:
    return {
        "coverage": name,
        "effective_date": eff.isoformat(),
        **pr.as_dict(),
        "previously_booked_cents": booked,
        "delta_cents": pr.amount_cents - booked,
        "formula": (
            f"{usd(pr.term_premium_cents)} × {pr.covered_days}/{pr.term_days} days "
            f"= {usd(pr.amount_cents)}"
        ),
    }
