"""Schema. Financial rows are append-only: nothing in `ledger_entries` is ever updated or
deleted. Corrections add new rows that point back at the action that caused them."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, utcnow


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(20))  # broker | customer
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(30), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)  # exclusive: first day NOT covered
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | cancelled
    cancelled_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    customer: Mapped[Customer] = relationship()
    coverages: Mapped[list[Coverage]] = relationship(
        back_populates="policy", order_by="Coverage.id"
    )


class Coverage(Base):
    """A coverage line (e.g. Cyber $1M) on a policy. Its *dates* live in CoverageVersion."""

    __tablename__ = "coverages"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    limit: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(10))  # base | rider
    term_premium_cents: Mapped[int] = mapped_column(Integer)  # full-term price
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    policy: Mapped[Policy] = relationship(back_populates="coverages")
    versions: Mapped[list[CoverageVersion]] = relationship(
        back_populates="coverage", order_by="CoverageVersion.id"
    )

    @property
    def current(self) -> CoverageVersion:
        return next(v for v in reversed(self.versions) if v.is_current)


class CoverageVersion(Base):
    """Bitemporal record: `effective_date` = when coverage applies; `recorded_at` = when we
    learned/entered it. A correction adds a version and flips the old one to not-current."""

    __tablename__ = "coverage_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    coverage_id: Mapped[int] = mapped_column(ForeignKey("coverages.id"), index=True)
    effective_date: Mapped[date] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    recorded_by: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, default="")
    action_id: Mapped[int | None] = mapped_column(ForeignKey("actions.id"), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)

    coverage: Mapped[Coverage] = relationship(back_populates="versions")


class Action(Base):
    """Audit trail: one row per business action. Ledger entries point back at these."""

    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class LedgerEntry(Base):
    """Signed amounts from the customer's perspective: positive = customer owes more,
    negative = customer owes less. Balance (amount due) = SUM(amount_cents)."""

    __tablename__ = "ledger_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    action_id: Mapped[int] = mapped_column(ForeignKey("actions.id"))
    type: Mapped[str] = mapped_column(String(20))  # CHARGE|ADJUSTMENT|CREDIT|PAYMENT|REFUND
    amount_cents: Mapped[int] = mapped_column(Integer)
    coverage_id: Mapped[int | None] = mapped_column(ForeignKey("coverages.id"), nullable=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"), nullable=True)
    refund_id: Mapped[int | None] = mapped_column(ForeignKey("refunds.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    calc: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    action: Mapped[Action] = relationship()


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    provider: Mapped[str] = mapped_column(String(20))  # fake | stripe
    provider_ref: Mapped[str] = mapped_column(String(100), unique=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|succeeded|failed
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"), index=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    provider_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|succeeded|failed
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WebhookEvent(Base):
    """Processed provider events, keyed by provider event id, for idempotency + evidence."""

    __tablename__ = "webhook_events"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailLog(Base):
    __tablename__ = "email_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int | None] = mapped_column(ForeignKey("policies.id"), nullable=True)
    to: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    template: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))  # sent | logged | failed
    provider_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
