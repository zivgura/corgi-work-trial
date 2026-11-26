# Integrations: live vs simulated

| Service | Purpose | Mode | How to switch |
|---|---|---|---|
| Stripe (test mode) | Collect premium (PaymentIntents), refunds, webhooks | **Simulated by default.** Live when `PAYMENT_PROVIDER=stripe` | keys below |
| Resend | Transactional email (issued, payment, correction, cancellation, refund) | **Simulated by default** (logged). Live when `EMAIL_PROVIDER=resend` | key below |

The UI shows the active mode in the header of every page and on **Broker → Integrations**, which also lists every provider event and email as evidence (screenshots for the submission come from here and from the Stripe/Resend dashboards).

> Status honesty: until real test keys are configured, both integrations run in simulated mode. The Stripe code path is implemented against the Stripe API but must be verified against a real test account before it can be called "live".

## Stripe test mode
1. Create a free Stripe account, stay in **Test mode**. Copy the *Publishable key* (`pk_test_…`) and *Secret key* (`sk_test_…`). The app refuses any non-test secret key.
2. Add a webhook endpoint `https://<your-host>/api/webhooks/stripe` with events: `payment_intent.succeeded`, `payment_intent.payment_failed`, `charge.refunded`. Copy its signing secret (`whsec_…`).
   - Local development: `stripe listen --forward-to localhost:8000/api/webhooks/stripe` prints a `whsec_…`.
3. Set `PAYMENT_PROVIDER=stripe`, `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`.
4. Test cards: `4242 4242 4242 4242` (succeeds), `4000 0000 0000 0002` (declined), any future expiry/CVC.

Flow: customer clicks Pay → server creates a PaymentIntent for the amount due (status *pending*) → Stripe Elements confirms → Stripe sends a signed webhook → `apply_provider_event()` marks it succeeded/failed and, on success, appends the `PAYMENT` ledger entry. Refunds call the Refunds API synchronously and append a `REFUND` entry.

## Resend
1. Create a Resend API key. Without a verified domain, use the default `onboarding@resend.dev` sender and send only to your own address or Resend's test addresses (`delivered@resend.dev`).
2. Set `EMAIL_PROVIDER=resend`, `RESEND_API_KEY`. Use a customer email such as `delivered@resend.dev` when creating the demo customer.

## Evidence checklist for the submission
- Stripe Dashboard → Developers → Events/Webhooks (payment_intent.succeeded, payment_intent.payment_failed, refunds) + the PaymentIntent for the $70 correction payment.
- Resend dashboard → Emails list.
- App → Broker → Integrations screenshot showing LIVE badges, provider events, and email log.
