"""Demo users + a one-click scenario so a reviewer can try the correction immediately."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import services as svc
from .models import Customer, User
from .security import hash_password

BROKER_EMAIL, BROKER_PASSWORD = "broker@corgi-demo.test", "corgi-demo-broker"
CUSTOMER_EMAIL, CUSTOMER_PASSWORD = "ada@acme-ai.test", "corgi-demo-customer"


def seed_users(db: Session) -> None:
    if db.scalar(select(User).where(User.email == BROKER_EMAIL)):
        return
    db.add(
        User(
            email=BROKER_EMAIL,
            name="Bea Broker",
            role="broker",
            password_hash=hash_password(BROKER_PASSWORD),
        )
    )
    c = Customer(name="Acme AI, Inc.", contact_name="Ada Founder", email=CUSTOMER_EMAIL)
    db.add(c)
    db.flush()
    db.add(
        User(
            email=CUSTOMER_EMAIL,
            name="Ada Founder",
            role="customer",
            customer_id=c.id,
            password_hash=hash_password(CUSTOMER_PASSWORD),
        )
    )
    db.commit()


def _settle(db: Session, actor: svc.Actor, policy) -> None:
    """Mark the open payment as paid via the same event path a real webhook uses."""
    pay = svc.create_payment(db, actor, policy)
    svc.apply_provider_event(
        db,
        svc.ProviderEvent(
            f"evt_seed_{uuid.uuid4().hex[:10]}",
            "payment_succeeded",
            pay.provider_ref,
            provider="fake",
        ),
    )


def load_scenario(db: Session, actor: svc.Actor, customer: Customer):
    """Policy 2026 + Tech E&O added effective Mar 1, BOTH PAID (simulated payments), ready for
    the broker to correct the effective date to Feb 22."""
    policy = svc.issue_policy(
        db,
        actor,
        customer,
        date(2026, 1, 1),
        date(2027, 1, 1),
        [{"code": "general_liability", "limit": "1M"}],
    )
    _settle(db, actor, policy)
    svc.add_coverage(db, actor, policy, "tech_eo", "1M", date(2026, 3, 1), "Customer requested E&O")
    _settle(db, actor, policy)
    db.commit()
    return policy
