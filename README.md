# Policy administration — Corgi work trial, Track 1

A small platform where **brokers** issue and manage commercial insurance policies and **policyholders** follow their coverage, payments and refunds, with every dollar traceable to the action that caused it.

- Track: **1 · Policy administration**
- Decision log: [`docs/DECISIONS.md`](docs/DECISIONS.md) · Integrations (live vs simulated): [`docs/INTEGRATIONS.md`](docs/INTEGRATIONS.md)
- Stack: React + TypeScript + Vite + Tailwind · FastAPI + SQLAlchemy · Postgres (SQLite for local dev) · Stripe + Resend sandboxes · pytest + Playwright

## Demo accounts (sandbox, fictional data)
| Role | Email | Password |
|---|---|---|
| Broker | `broker@corgi-demo.test` | `corgi-demo-broker` |
| Policyholder | `ada@acme-ai.test` | `corgi-demo-customer` |

The login page has one-click buttons for both. The header of every page says whether payments/email are **simulated** or **live sandbox**.

## The scenario, in the app
1. Broker → **Policies → Load demo scenario** (simulated mode) or issue a policy yourself.
2. Customer has paid for the policy ($2,400.00) and for a coverage change: Tech E&O added effective **Mar 1** ($3,060.00).
3. Broker opens the policy → Tech E&O → **Correct start date** → **Feb 22**, with a reason. The preview shows `$3,650.00 × 313/365 days = $3,130.00 − already charged $3,060.00 = +$70.00` before anything is saved.
4. Statement now shows the **original $3,060.00 charge, untouched**, plus a separate **Correction +$70.00**, and **$70.00 due**. Click any line for its formula, the action behind it, who did it, and why.
5. Customer sees the same statement plus a banner explaining what changed, and can pay the $70.00.
6. Broker cancels effective Jul 1 → pro-rata refund of unearned premium to the original payment method.

### Worked numbers
Term Jan 1 2026 → Jan 1 2027 (365 days). Tech E&O $1M = $3,650/yr = $10.00/day.
- Mar 1 → 306 days → **$3,060.00** · Feb 22 → 313 days → **$3,130.00** · correction **+$70.00**.
- Cancel Jul 1 after everything is paid ($5,530.00 net incl. the $70): base earned 181/365 × $2,400 = $1,190.14; Tech E&O earned 129 days × $10 = $1,290.00; refund = $5,530.00 − $2,480.14 = **$3,049.86**.

## How it works (the part worth reading)
- **Append-only ledger.** `ledger_entries` are never edited. Amount due = `SUM(amount_cents)`. Entry types: `CHARGE`, `ADJUSTMENT`, `CREDIT`, `PAYMENT`, `REFUND`; each points at an `Action` (who/what/when/why).
- **Bitemporal coverage.** `CoverageVersion` stores *effective date* (when cover applies) and *recorded at* (when we learned it). Corrections add a version; the old one stays visible.
- **`reconcile()`** recomputes expected premium per coverage from the current effective date and appends the difference. One path for charges, corrections and cancellation credits.
- **One event handler for payments** (`apply_provider_event`) used by Stripe's webhook and the simulated confirmation alike; idempotent on event id.
- **Previews** (`/policies/{id}/preview`) run the same maths without writing.

```
frontend (React) ──► FastAPI ──► services.py (rules) ──► pricing.py (pure maths)
                         │               │
                         │               └─► providers.py ──► Stripe (test) / Resend  | simulated
                         └─► SQLAlchemy ──► Postgres / SQLite
```

## Run it
```bash
# backend (simulated payments/email, SQLite)
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000
# frontend (proxies /api → :8000)
cd frontend && npm install && npm run dev        # http://localhost:5173
```
Or one container: `docker build -t corgi-policy-admin . && docker run -p 8000:8000 corgi-policy-admin` → http://localhost:8000. Config: [`.env.example`](.env.example). Deploy: [`render.yaml`](render.yaml).

## Tests
```bash
cd backend && uv run pytest -q                                   # 29 tests, SQLite
TEST_DATABASE_URL=postgresql://… uv run pytest -q                # same suite on Postgres
cd frontend && npm run build
cd e2e && npm install && CHROME_PATH=$(which google-chrome) npx playwright test   # full UI scenario + screenshots
```
The pytest suite pins the brief's numbers ($3,060 → $3,130, +$70, cancellation refund), idempotent webhooks, failed/pending/succeeded payments, role isolation, and rule violations. The Playwright test drives the real UI through issue → fail/succeed payment → add coverage → correct date → customer view → cancel/refund and saves screenshots to `e2e/screenshots/`.

## Simplified / not built
See [`docs/DECISIONS.md`](docs/DECISIONS.md#not-built-on-purpose). In short: one product line and a catalog price table (no underwriting), no claims/renewals/commissions/taxes/installments, minimal auth (no reset/MFA/invites), no migrations framework yet, no row-level locking for simultaneous edits. **Next I would build:** Alembic migrations, per-policy locking, short-rate cancellation option, COI PDF generation, renewals, and a reconciliation job that compares the ledger to Stripe's balance transactions.
