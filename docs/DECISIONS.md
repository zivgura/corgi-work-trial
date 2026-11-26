# Decision log

Dated, short. Each entry says what was decided, why, and what it costs.

## 2026-11-26

**Track 1, Policy administration.** One product line (commercial liability for startups), three coverages from a small catalog (General Liability core; Cyber and Tech E&O add-ons). Chosen because the brief's test (correct a back-dated effective date and explain the new amount) is a ledger problem, and I wanted the whole build to serve that.

**Append-only ledger; the balance is derived.** `ledger_entries` rows are never updated or deleted. Amount due is `SUM(amount_cents)`, not a stored number. Corrections add rows. This is what lets the customer see the original charge and the correction as separate lines, and what lets any amount be traced to the action behind it (`action_id`). Cost: reads do an aggregate; fine at this scale, and indexed by `policy_id`.

**`reconcile()` makes the ledger match the policy "as it is now".** After any action (issue, add coverage, correct date, cancel) it recomputes the expected premium per coverage from the *current* effective date and appends the difference against what is already booked. One code path covers charges, corrections and cancellation credits, so they cannot disagree with each other. Cost: it recomputes every coverage each time; trivial with a handful of coverages.

**Two dates per coverage change (bitemporal).** `effective_date` is when cover applies; `recorded_at` is when we learned it. A correction inserts a new `CoverageVersion` and flips the old one to not-current; nothing is overwritten. The broker UI shows the superseded date struck through; the customer sees a banner explaining what changed and why.

**Money is integer cents; dates are DATE, not datetimes.** No floats. No timezone arithmetic on coverage days.

**Pricing.** Catalog gives an annual (365-day) price per coverage and limit. A coverage's full-term premium is `annual × term_days / 365`. A coverage that starts mid-term is charged `term_premium × covered_days / term_days`, rounded half-up to the cent once per coverage (not per day). Covered days = `end − effective`, where the term end date is exclusive ("expires on", first day not covered). Worked example in README.

**Cancellation rule.** Pro-rata, effective 00:00 on the chosen date, unearned premium refunded to the original payment method(s); no short-rate penalty, no fee. A cancellation date on the start date is a flat cancel (full refund). Cancellation before an add-on's effective date earns nothing for that add-on. Alternative I did not build: short-rate (e.g. 90% of pro-rata) which insurers often use.

**Negative corrections create a credit, not an automatic refund.** If a correction moves a date *later*, the customer is owed money. The ledger balance goes negative ("credit on account") and the broker decides whether to refund it ("Refund credit"). On cancellation the refund is automatic because intent is clear.

**Refund amount is capped by cash actually received.** Refund = min(credit, paid − already refunded). If the customer never paid, a cancellation credit just reduces what they owe. Unpaid corrections net off against refunds (e.g. $70 unpaid reduces the refund by $70).

**Payments are state machines driven by one event handler.** `apply_provider_event()` is the only place payment/refund outcomes change state. Stripe's signed webhook and the simulated confirmation both call it, so the simulated path exercises the same code. Idempotent on provider event id; a payment already `succeeded` can't be double-booked by a second event. A payment may go `failed → succeeded` (Stripe lets a customer retry the same PaymentIntent).

**Payment attempts don't touch the ledger until they succeed.** Pending/failed attempts are shown separately on the statement ("Payment attempts not on the statement"). Only a succeeded payment appends a `PAYMENT` entry. If the amount due changes while a payment is pending, the old attempt is marked `canceled` and a new one is created; if the old one still succeeds later it is still booked (we took the money), and the balance shows the difference.

**Two integrations.** Stripe (PaymentIntents + Refunds + signed webhooks, test mode only; the provider refuses non-`sk_test_` keys) and Resend (transactional email). Each sits behind a small interface with a simulated implementation, so the app runs offline and the README states which mode is active. The UI shows LIVE vs SIMULATED badges everywhere it matters.

**Auth is deliberately minimal.** Seeded demo users, PBKDF2 password hashes, JWT bearer tokens, role checks on every route, customers can only read their own policies. No password reset, no MFA, no invites (broker sees a temporary password once). Called out as a simplification.

**No Alembic migrations (yet).** Schema is created with `create_all` on startup. Fine for a throwaway demo database; the first thing I would add for a real deployment.

**SQLite in dev, Postgres in prod.** Same SQLAlchemy code; the whole test suite runs against both (SQLite in-memory, and a real Postgres 16 locally and in CI).

**UI.** Design tokens read from corgi.insure (orange #ff5c00, ink #1d1d1d, canvas #f6f6f6, 0.5rem radius, Geist, italic serif accent). Original wordmark and icons only; no Corgi logos or mascot artwork. Every statement line expands to show the formula and the action/actor/reason behind it ("explain this amount"). Broker actions show a live preview of the amount *before* confirming.

## Not built (on purpose)
Claims, renewals, broker commissions, endorsements other than adding coverage / correcting its start date, premium taxes/fees, multi-currency, installment plans, document (COI) generation, password reset/MFA, concurrency control beyond DB transactions (two brokers editing one policy at the same instant could interleave; a row lock on the policy in `reconcile` is the fix).
