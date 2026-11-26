"""The assignment's headline scenario, end to end at the service layer.

Customer pays for the policy and for a coverage change. Later the broker finds the extra
coverage began a week earlier than recorded. Correct the date; keep the original charge and
the correction visible; show the revised amount due.
"""

from datetime import date

import pytest
from sqlalchemy import select

from app import services as svc
from app.models import LedgerEntry, Payment
from app.services import DomainError, ProviderEvent

from .conftest import BROKER, END, START


def issue(db, customer, items=None):
    items = items or [{"code": "general_liability", "limit": "1M"}]
    p = svc.issue_policy(db, BROKER, customer, START, END, items)
    db.commit()
    return p


def pay_in_full(db, policy, ok=True, event_id=None):
    pay = svc.create_payment(db, BROKER, policy)
    ev = ProviderEvent(
        id=event_id or f"evt_{pay.id}_{'ok' if ok else 'bad'}",
        type="payment_succeeded" if ok else "payment_failed",
        ref=pay.provider_ref,
        failure_reason=None if ok else "Your card was declined.",
        provider="fake",
    )
    svc.apply_provider_event(db, ev)
    db.commit()
    return pay


def entries(db, policy):
    return db.scalars(
        select(LedgerEntry).where(LedgerEntry.policy_id == policy.id).order_by(LedgerEntry.id)
    ).all()


def test_issue_creates_charge_and_balance(db, customer):
    p = issue(db, customer)
    es = entries(db, p)
    assert [(e.type, e.amount_cents) for e in es] == [("CHARGE", 240_000)]
    assert svc.balance(db, p.id) == 240_000


def test_payment_states_pending_success_failed(db, customer):
    p = issue(db, customer)
    pay = svc.create_payment(db, BROKER, p)
    assert pay.status == "pending" and pay.amount_cents == 240_000
    # a second request while one is open reuses it (idempotent)
    assert svc.create_payment(db, BROKER, p).id == pay.id
    assert svc.balance(db, p.id) == 240_000  # pending does not move the ledger

    svc.apply_provider_event(
        db, ProviderEvent("e1", "payment_failed", pay.provider_ref, "declined", "fake")
    )
    assert db.get(Payment, pay.id).status == "failed"
    assert svc.balance(db, p.id) == 240_000  # still owed

    pay2 = svc.create_payment(db, BROKER, p)
    assert pay2.id != pay.id
    svc.apply_provider_event(db, ProviderEvent("e2", "payment_succeeded", pay2.provider_ref))
    assert db.get(Payment, pay2.id).status == "succeeded"
    assert svc.balance(db, p.id) == 0


def test_reused_payment_attempt_gets_its_client_secret_again(db, customer):
    """Regression: the Stripe client secret is never stored. A reused pending attempt used to come
    back without one, so the customer's browser could not render the card form and got stuck."""
    from app.providers import FakeProvider, set_payment_provider

    class SecretProvider(FakeProvider):
        name = "fake"

        def client_secret_for(self, payment_ref):
            return f"{payment_ref}_secret_xyz"

    set_payment_provider(SecretProvider())
    p = issue(db, customer)
    first = svc.create_payment(db, BROKER, p)
    again = svc.create_payment(db, BROKER, p)
    assert again.id == first.id
    assert again.client_secret == f"{first.provider_ref}_secret_xyz"


def test_pending_attempt_from_another_provider_mode_is_not_reused(db, customer):
    p = issue(db, customer)
    old = svc.create_payment(db, BROKER, p)
    old.provider = "stripe"  # pretend it was created while the app ran in Stripe mode
    db.commit()
    fresh = svc.create_payment(db, BROKER, p)  # provider is now the simulated one
    assert fresh.id != old.id and db.get(Payment, old.id).status == "canceled"


class _ProviderSays:
    """Stand-in for Stripe whose answer to "what happened to this payment?" we control."""

    def __init__(self, state, reason=None):
        from app.providers import FakeProvider, PaymentState

        self._fake = FakeProvider()
        self.name = "fake"
        self._state = PaymentState(state, reason)

    def __getattr__(self, item):
        return getattr(self._fake, item)

    def payment_state(self, ref):
        return self._state


def test_lost_webhook_is_reconciled_and_a_late_webhook_does_not_double_book(db, customer):
    """Stripe took the money but our webhook never arrived. Asking the provider books it once."""
    from app.providers import set_payment_provider

    p = issue(db, customer)
    pay = svc.create_payment(db, BROKER, p)
    db.commit()
    set_payment_provider(_ProviderSays("succeeded"))
    assert svc.sync_pending_payments(db, p) is True
    assert db.get(Payment, pay.id).status == "succeeded"
    assert svc.balance(db, p.id) == 0
    # the real webhook shows up afterwards: nothing changes
    out = svc.apply_provider_event(
        db, ProviderEvent("evt_late", "payment_succeeded", pay.provider_ref, provider="fake")
    )
    assert out == "duplicate" and svc.balance(db, p.id) == 0
    assert svc.sync_pending_payments(db, p) is False  # idempotent
    payments = [e for e in db.scalars(select(LedgerEntry)) if e.type == "PAYMENT"]
    assert len(payments) == 1


def test_concurrent_webhook_and_reconciliation_book_a_payment_only_once(db, customer):
    """Regression: a signed webhook and a polled reconciliation handled the same Stripe payment
    in parallel (each read 'pending') and booked it twice. The second one must lose."""
    from sqlalchemy.orm import sessionmaker

    p = issue(db, customer)
    pay = svc.create_payment(db, BROKER, p)
    db.commit()
    other = sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False)()
    stale = other.scalar(select(Payment).where(Payment.id == pay.id))
    assert stale is not None and stale.status == "pending"  # the other request's stale view
    first = svc.apply_provider_event(
        db, ProviderEvent("evt_web", "payment_succeeded", pay.provider_ref, provider="fake")
    )
    db.commit()
    second = svc.apply_provider_event(
        other,
        ProviderEvent("sync_x_succeeded", "payment_succeeded", pay.provider_ref, provider="fake"),
    )
    other.commit()
    other.close()
    assert (first, second) == ("applied", "duplicate")
    entries = [e for e in db.scalars(select(LedgerEntry)) if e.type == "PAYMENT"]
    assert len(entries) == 1 and svc.balance(db, p.id) == 0
    from app.models import EmailLog

    mails = [m for m in db.scalars(select(EmailLog)) if m.template == "payment_received"]
    assert len(mails) == 1


def test_paid_policy_is_not_offered_a_second_payment(db, customer):
    from app.providers import set_payment_provider

    p = issue(db, customer)
    svc.create_payment(db, BROKER, p)
    db.commit()
    set_payment_provider(_ProviderSays("succeeded"))
    with pytest.raises(DomainError, match="Nothing is due"):
        svc.create_payment(db, BROKER, p)


def test_reconciliation_handles_failed_and_canceled_attempts(db, customer):
    from app.providers import set_payment_provider

    p = issue(db, customer)
    a = svc.create_payment(db, BROKER, p)
    db.commit()
    set_payment_provider(_ProviderSays("failed", "Your card was declined."))
    svc.sync_pending_payments(db, p)
    assert db.get(Payment, a.id).status == "failed"
    assert db.get(Payment, a.id).failure_reason == "Your card was declined."
    assert svc.balance(db, p.id) == 240_000  # still owed

    set_payment_provider(_ProviderSays("canceled"))
    b = svc.create_payment(db, BROKER, p)  # a new attempt, since the failed one is over
    set_payment_provider(_ProviderSays("canceled"))
    svc.sync_pending_payments(db, p)
    assert db.get(Payment, b.id).status == "canceled"


def test_webhook_is_idempotent(db, customer):
    p = issue(db, customer)
    pay = svc.create_payment(db, BROKER, p)
    ev = ProviderEvent("same-id", "payment_succeeded", pay.provider_ref)
    assert svc.apply_provider_event(db, ev) == "applied"
    assert svc.apply_provider_event(db, ev) == "duplicate"
    # a different event id for an already-succeeded payment must not double count either
    assert (
        svc.apply_provider_event(
            db, ProviderEvent("other-id", "payment_succeeded", pay.provider_ref)
        )
        == "duplicate"
    )
    assert svc.balance(db, p.id) == 0
    assert len([e for e in entries(db, p) if e.type == "PAYMENT"]) == 1


def test_headline_scenario_correction_keeps_original_and_shows_70_due(db, customer):
    p = issue(db, customer)
    pay_in_full(db, p)  # pays $2,400.00 base premium
    assert svc.balance(db, p.id) == 0

    # Add Tech E&O ($3,650/yr) effective Mar 1 -> 306 days -> $3,060.00 due, then paid.
    svc.add_coverage(db, BROKER, p, "tech_eo", "1M", date(2026, 3, 1), "Customer requested")
    db.commit()
    assert svc.balance(db, p.id) == 306_000
    pay_in_full(db, p)
    assert svc.balance(db, p.id) == 0

    rider = next(c for c in p.coverages if c.code == "tech_eo")

    # Weeks later: coverage actually began Feb 22 (a week earlier).
    svc.correct_effective_date(
        db, BROKER, p, rider.id, date(2026, 2, 22), "Binder confirms start was Feb 22"
    )
    db.commit()

    # Revised amount due: exactly 7 more days at $10/day.
    assert svc.balance(db, p.id) == 7_000

    st = svc.statement(db, p)
    rows = [(r["type"], r["amount_cents"]) for r in st["rows"]]
    assert rows == [
        ("CHARGE", 240_000),  # base premium
        ("PAYMENT", -240_000),
        ("CHARGE", 306_000),  # ORIGINAL rider charge: still there, untouched
        ("PAYMENT", -306_000),
        ("ADJUSTMENT", 7_000),  # the correction, as its own line
    ]
    adj = st["rows"][-1]
    assert "Feb 22, 2026" in adj["explanation"] and "Mar 1, 2026" in adj["explanation"]
    assert "$3,130.00" in adj["explanation"] and "$3,060.00" in adj["explanation"]
    assert adj["action"]["kind"] == "CORRECT_EFFECTIVE_DATE"
    assert adj["action"]["note"] == "Binder confirms start was Feb 22"

    # Both versions of the coverage date remain on record (bitemporal)
    d = svc.policy_detail(db, p)
    versions = next(c for c in d["coverages"] if c["code"] == "tech_eo")["versions"]
    assert [(v["effective_date"], v["is_current"]) for v in versions] == [
        ("2026-03-01", False),
        ("2026-02-22", True),
    ]

    # The customer can pay the $70 difference
    pay = svc.create_payment(db, BROKER, p)
    assert pay.amount_cents == 7_000


def test_debrief_change_date_again_recalculates_from_ledger(db, customer):
    """They'll change the date live: correct twice and check every number still ties out."""
    p = issue(db, customer, [{"code": "tech_eo", "limit": "1M"}])
    pay_in_full(db, p)
    cov = p.coverages[0]
    svc.correct_effective_date(db, BROKER, p, cov.id, date(2026, 3, 1), "first fix")  # -$600
    assert svc.balance(db, p.id) == -(365_000 - 306_000)  # credit of $590.00
    svc.correct_effective_date(db, BROKER, p, cov.id, date(2026, 2, 22), "second fix")
    assert svc.balance(db, p.id) == -(365_000 - 313_000)  # credit of $520.00
    types = [e.type for e in entries(db, p)]
    assert types == ["CHARGE", "PAYMENT", "ADJUSTMENT", "ADJUSTMENT"]
    assert sum(e.amount_cents for e in entries(db, p)) == svc.balance(db, p.id)


def test_negative_correction_creates_credit_that_can_be_refunded(db, customer):
    p = issue(db, customer, [{"code": "tech_eo", "limit": "1M"}])
    pay_in_full(db, p)
    cov = p.coverages[0]
    svc.correct_effective_date(db, BROKER, p, cov.id, date(2026, 3, 1), "started later")
    assert svc.balance(db, p.id) == -59_000
    refunds = svc.issue_refund(db, BROKER, p)
    db.commit()
    assert [r.amount_cents for r in refunds] == [59_000]
    assert svc.balance(db, p.id) == 0
    assert db.get(Payment, refunds[0].payment_id).refunded_cents == 59_000


def test_cancellation_refunds_unearned_premium_after_correction(db, customer):
    p = issue(db, customer)
    pay_in_full(db, p)
    svc.add_coverage(db, BROKER, p, "tech_eo", "1M", date(2026, 3, 1))
    pay_in_full(db, p)
    rider = next(c for c in p.coverages if c.code == "tech_eo")
    svc.correct_effective_date(db, BROKER, p, rider.id, date(2026, 2, 22), "typo")
    pay_in_full(db, p)  # pays the $70
    paid_total = 240_000 + 306_000 + 7_000
    assert svc.balance(db, p.id) == 0

    out = svc.cancel_policy(db, BROKER, p, date(2026, 7, 1), "Customer shut down")
    db.commit()

    # base earned: 240,000 * 181/365 = 119,014 ; rider earned: 10,00 * 129 days = 129,000
    earned = 119_014 + 129_000
    expected_refund = paid_total - earned
    assert expected_refund == 304_986  # $3,049.86
    assert p.status == "cancelled"
    assert sum(r.amount_cents for r in out["refunds"]) == expected_refund
    assert svc.balance(db, p.id) == 0
    st = svc.statement(db, p)
    assert st["totals"]["net_premium_cents"] == earned
    assert st["totals"]["paid_cents"] - st["totals"]["refunded_cents"] == earned
    # Credits are on their own lines, originals untouched
    assert [r["type"] for r in st["rows"]].count("CREDIT") == 2
    assert st["rows"][0]["type"] == "CHARGE" and st["rows"][0]["amount_cents"] == 240_000


def test_cancel_unpaid_policy_leaves_amount_due_and_no_refund(db, customer):
    p = issue(db, customer)
    out = svc.cancel_policy(db, BROKER, p, date(2026, 7, 1))
    assert out["refunds"] == []
    assert svc.balance(db, p.id) == 119_014  # earned premium still owed


def test_flat_cancellation_on_start_date_refunds_everything(db, customer):
    p = issue(db, customer)
    pay_in_full(db, p)
    svc.cancel_policy(db, BROKER, p, START)
    assert svc.balance(db, p.id) == 0
    assert sum(e.amount_cents for e in entries(db, p) if e.type == "REFUND") == 240_000


def test_rules_are_enforced(db, customer):
    p = issue(db, customer)
    with pytest.raises(DomainError):  # nothing due after... it IS due; pay then try again
        pay_in_full(db, p)
        svc.create_payment(db, BROKER, p)
    with pytest.raises(DomainError):
        svc.add_coverage(db, BROKER, p, "general_liability", "1M", date(2026, 3, 1))  # duplicate
    with pytest.raises(DomainError):
        svc.add_coverage(db, BROKER, p, "cyber", "1M", date(2025, 1, 1))  # before term
    cov = p.coverages[0]
    with pytest.raises(DomainError):
        svc.correct_effective_date(db, BROKER, p, cov.id, date(2026, 2, 1), "")  # reason required
    with pytest.raises(DomainError):
        svc.correct_effective_date(db, BROKER, p, cov.id, START, "same date")  # unchanged
    with pytest.raises(DomainError):
        svc.cancel_policy(db, BROKER, p, END)  # not within term
    svc.cancel_policy(db, BROKER, p, date(2026, 6, 1))
    with pytest.raises(DomainError):
        svc.cancel_policy(db, BROKER, p, date(2026, 7, 1))  # already cancelled
    with pytest.raises(DomainError):
        svc.add_coverage(db, BROKER, p, "cyber", "1M", date(2026, 3, 1))  # cancelled


def test_emails_are_logged_for_each_step(db, customer):
    from app.models import EmailLog

    p = issue(db, customer)
    pay_in_full(db, p)
    templates = [e.template for e in db.scalars(select(EmailLog).order_by(EmailLog.id))]
    assert templates == ["policy_issued", "payment_received"]


def test_emails_carry_a_branded_html_version(db, customer):
    from app.email_html import render_email_html
    from app.providers import EmailResult, set_email_provider

    sent: list[dict] = []

    class Capture:
        name = "capture"

        def send(self, to, subject, body, html=None):
            sent.append({"to": to, "subject": subject, "body": body, "html": html})
            return EmailResult(status="logged")

    set_email_provider(Capture())
    p = issue(db, customer)
    assert sent and sent[0]["html"]
    html = sent[0]["html"]
    assert p.number in html and "#ff5c00" in html and "Open your portal" in html
    assert f"/portal/policies/{p.id}" in html and "— Corgi (demo)" not in html
    # untrusted text is escaped
    out = render_email_html("payment_failed", "x", "<script>alert(1)</script>", "http://x")
    assert "<script>" not in out and "&lt;script&gt;" in out


def test_sandbox_redirect_delivers_elsewhere_but_logs_the_real_recipient(db, customer, monkeypatch):
    from app.config import get_settings
    from app.models import EmailLog
    from app.providers import EmailResult, set_email_provider

    sent: list[dict] = []

    class Capture:
        name = "capture"

        def send(self, to, subject, body, html=None):
            sent.append({"to": to, "subject": subject, "body": body, "html": html})
            return EmailResult(status="sent", provider_id="x")

    set_email_provider(Capture())
    monkeypatch.setattr(get_settings(), "email_redirect_to", "owner@demo.test")
    issue(db, customer)
    assert sent[0]["to"] == "owner@demo.test"
    assert customer.email in sent[0]["subject"] and customer.email in sent[0]["html"]
    log = db.scalars(select(EmailLog)).first()
    assert log.to == customer.email and not log.subject.startswith("[to ")
