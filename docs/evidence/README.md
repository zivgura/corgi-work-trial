# Sandbox-integration evidence

Captured 2026-11-27 on the deployed app (https://corgi-policy-admin-tihx.onrender.com) with live Stripe test mode and live Resend (sandbox sender).

| File | What it shows |
|---|---|
| 01-integrations-live-events-emails.jpg | Integrations page: both providers LIVE; signed Stripe events (`evt_…`) for 3 payments and 1 refund; emails with Resend message ids, status `sent` |
| 02-card-only-payment-form.jpg | Customer payment form: Stripe Elements, card only |
| 03-add-coverage-preview.jpg | Broker adds Tech E&O mid-term, effective 2026-03-01: preview $3,650 × 306/365 = $3,060 before anything is saved |
| 04-coverage-added-ledger.jpg | Ledger after adding coverage: +$3,060 charge, original payment kept |
| 05-customer-paid-both-charges.jpg | Customer view: second payment of $3,060 booked, $0 due |
| 06-correction-preview.jpg | Date correction preview: start Mar 1 → Feb 22, $3,650 × 313/365 = $3,130, already charged $3,060, +$70 |
| 07-correction-applied-original-kept.jpg | After correction: original charge and payment kept, separate Correction line +$70, $70 due |
| 08-date-history-and-ledger.jpg | Bitemporal date history: Mar 1 superseded, Feb 22 current, who recorded it and why |
| 09-cancel-preview-prorata-refund.jpg | Cancellation effective 2027-02-27: $2,400 × 92/365 = $604.93 earned, refund $1,795.07 |
| 10-cancel-refund-ledger.jpg | Ledger after cancel + refund: Charge, Payment, Credit, Refund; balance $0, Refunded $1,795.07 |
| 11-stripe-api-log-refund-400-then-200.jpg | Stripe request log: two refund calls rejected (idempotency key reused by another database), then 200 after the key fix (see DECISIONS.md) |
| 12-test-run.txt | Backend test suite result |
