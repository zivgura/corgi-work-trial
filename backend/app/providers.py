"""External services behind small interfaces so the business logic never imports Stripe/Resend.

Payments: StripeProvider (test mode, LIVE sandbox) or FakeProvider (SIMULATED, no network).
Email:    ResendProvider (sandbox/test recipients, LIVE) or FakeEmail (logs only, SIMULATED).
Both modes feed the *same* event handler in services.py, so the state machine is identical.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings, get_settings


class ProviderError(RuntimeError):
    pass


@dataclass
class PaymentIntentResult:
    ref: str
    client_secret: str | None = None


@dataclass
class PaymentState:
    state: str  # pending | succeeded | failed | canceled
    failure_reason: str | None = None


class PaymentProvider(Protocol):
    name: str

    def create_payment(
        self, amount_cents: int, description: str, metadata: dict[str, str]
    ) -> PaymentIntentResult: ...

    def client_secret_for(self, payment_ref: str) -> str | None: ...

    def payment_state(self, payment_ref: str) -> PaymentState: ...

    def refund(self, payment_ref: str, amount_cents: int, idempotency_key: str) -> str: ...


class FakeProvider:
    """Simulated payments. Confirmation is triggered by /payments/{id}/simulate, which feeds
    the same event handler that real Stripe webhooks use."""

    name = "fake"
    _counter = itertools.count(1)

    def create_payment(self, amount_cents, description, metadata) -> PaymentIntentResult:
        return PaymentIntentResult(ref=f"pi_sim_{uuid.uuid4().hex[:16]}")

    def client_secret_for(self, payment_ref) -> str | None:
        return None  # simulated payments have no browser-side card form

    def payment_state(self, payment_ref) -> PaymentState:
        return PaymentState("pending")  # simulated payments resolve only via /simulate

    def refund(self, payment_ref, amount_cents, idempotency_key) -> str:
        return f"re_sim_{uuid.uuid4().hex[:16]}"


class StripeProvider:
    """Stripe TEST MODE. PaymentIntents + Refunds; confirmation arrives by signed webhook."""

    name = "stripe"

    def __init__(self, settings: Settings):
        import stripe

        if not settings.stripe_secret_key.startswith(("sk_test_", "rk_test_")):
            raise ProviderError("Refusing to use a non-test Stripe key (expected sk_test_...)")
        stripe.api_key = settings.stripe_secret_key
        self._stripe = stripe

    def create_payment(self, amount_cents, description, metadata) -> PaymentIntentResult:
        try:
            pi = self._stripe.PaymentIntent.create(
                amount=amount_cents,
                currency="usd",
                description=description,
                metadata=metadata,
                automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
            )
        except self._stripe.StripeError as exc:  # pragma: no cover - network
            raise ProviderError(str(exc)) from exc
        return PaymentIntentResult(ref=pi.id, client_secret=pi.client_secret)

    def client_secret_for(self, payment_ref) -> str | None:
        """The secret is not stored by us; re-fetch it so a reused attempt can still show the card form."""
        try:
            return self._stripe.PaymentIntent.retrieve(payment_ref).client_secret
        except self._stripe.StripeError as exc:  # pragma: no cover - network
            raise ProviderError(str(exc)) from exc

    def payment_state(self, payment_ref) -> PaymentState:
        """Ask Stripe what actually happened to this PaymentIntent (used when a webhook is late or lost)."""
        try:
            pi = self._stripe.PaymentIntent.retrieve(payment_ref)
        except self._stripe.StripeError as exc:  # pragma: no cover - network
            raise ProviderError(str(exc)) from exc
        if pi.status == "succeeded":
            return PaymentState("succeeded")
        if pi.status == "canceled":
            return PaymentState("canceled")
        err = getattr(pi, "last_payment_error", None)
        if pi.status == "requires_payment_method" and err:
            return PaymentState("failed", getattr(err, "message", None) or "Card declined")
        return PaymentState("pending")  # not yet submitted, or still processing

    def refund(self, payment_ref, amount_cents, idempotency_key) -> str:
        try:
            r = self._stripe.Refund.create(
                payment_intent=payment_ref,
                amount=amount_cents,
                idempotency_key=idempotency_key,
            )
        except self._stripe.StripeError as exc:  # pragma: no cover - network
            raise ProviderError(str(exc)) from exc
        return r.id


_payment_provider: PaymentProvider | None = None


def get_payment_provider() -> PaymentProvider:
    global _payment_provider
    if _payment_provider is None:
        s = get_settings()
        _payment_provider = StripeProvider(s) if s.payment_provider == "stripe" else FakeProvider()
    return _payment_provider


def set_payment_provider(p: PaymentProvider | None) -> None:
    global _payment_provider
    _payment_provider = p


# ---- email ---------------------------------------------------------------------------------


@dataclass
class EmailResult:
    status: str  # sent | logged | failed
    provider_id: str | None = None
    error: str | None = None


class EmailProvider(Protocol):
    name: str

    def send(self, to: str, subject: str, body: str, html: str | None = None) -> EmailResult: ...


class FakeEmail:
    name = "fake"

    def send(self, to, subject, body, html=None) -> EmailResult:
        return EmailResult(status="logged")


class ResendEmail:
    name = "resend"

    def __init__(self, settings: Settings):
        self.key = settings.resend_api_key
        self.sender = settings.email_from

    def send(self, to, subject, body, html=None) -> EmailResult:  # pragma: no cover - network
        try:
            r = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "from": self.sender,
                    "to": [to],
                    "subject": subject,
                    "text": body,
                    **({"html": html} if html else {}),
                },
                timeout=10,
            )
            if r.status_code >= 300:
                return EmailResult(status="failed", error=f"{r.status_code}: {r.text[:300]}")
            return EmailResult(status="sent", provider_id=r.json().get("id"))
        except httpx.HTTPError as exc:
            return EmailResult(status="failed", error=str(exc))


_email_provider: EmailProvider | None = None


def get_email_provider() -> EmailProvider:
    global _email_provider
    if _email_provider is None:
        s = get_settings()
        _email_provider = ResendEmail(s) if s.email_provider == "resend" else FakeEmail()
    return _email_provider


def set_email_provider(p: EmailProvider | None) -> None:
    global _email_provider
    _email_provider = p
