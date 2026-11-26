"""Pure pricing rules. No database, no I/O: everything here is deterministic and unit tested.

Conventions (also recorded in docs/DECISIONS.md):
- Money is integer cents (USD). Never floats.
- A policy term is [start_date, end_date): the start day is covered, the end date is the
  first day NOT covered ("expires on"). Day count = (end - start).days.
- Each coverage has a full-term premium. A coverage that takes effect part-way through the
  term is charged pro-rata: term_premium * days_covered / term_days.
- Rounding: half-up to the nearest cent, done once per coverage per calculation
  (never per day), using integer arithmetic.
- Cancellation: pro-rata. Coverage ends at 00:00 on the cancellation date; unearned premium
  is refunded, no short-rate penalty, no fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# --- catalog -----------------------------------------------------------------------------
# Annual (365-day) list prices in cents, by coverage code and limit. Fictional, in the range
# Corgi publishes for early-stage startups.
CATALOG: dict[str, dict[str, object]] = {
    "general_liability": {
        "name": "General Liability",
        "kind": "base",
        "limits": {"1M": 240_000, "2M": 340_000},
    },
    "cyber": {
        "name": "Cyber Liability",
        "kind": "rider",
        "limits": {"1M": 180_000, "2M": 290_000},
    },
    "tech_eo": {
        "name": "Tech E&O",
        "kind": "rider",
        "limits": {"1M": 365_000, "2M": 520_000},
    },
}


class PricingError(ValueError):
    pass


def term_days(start: date, end: date) -> int:
    days = (end - start).days
    if days <= 0:
        raise PricingError("Policy end date must be after the start date")
    return days


def round_div(numerator: int, denominator: int) -> int:
    """Integer division rounded half-up (for non-negative numerator, positive denominator)."""
    if denominator <= 0:
        raise PricingError("denominator must be positive")
    if numerator < 0:
        raise PricingError("numerator must be non-negative")
    return (2 * numerator + denominator) // (2 * denominator)


def term_premium(code: str, limit: str, start: date, end: date) -> int:
    """Full-term premium in cents: annual list price scaled by term length / 365."""
    try:
        annual = int(CATALOG[code]["limits"][limit])  # type: ignore[index]
    except KeyError as exc:
        raise PricingError(f"Unknown coverage {code!r} / limit {limit!r}") from exc
    return round_div(annual * term_days(start, end), 365)


@dataclass(frozen=True)
class Proration:
    """Everything needed to explain a pro-rata amount to a human."""

    term_premium_cents: int
    term_days: int
    effective_date: date
    end_date: date  # coverage end used for this calculation (term end or cancellation date)
    covered_days: int
    amount_cents: int

    def as_dict(self) -> dict:
        return {
            "term_premium_cents": self.term_premium_cents,
            "term_days": self.term_days,
            "effective_date": self.effective_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "covered_days": self.covered_days,
            "amount_cents": self.amount_cents,
        }


def prorate(
    term_premium_cents: int,
    term_start: date,
    term_end: date,
    effective: date,
    cancelled_on: date | None = None,
) -> Proration:
    """Premium earned for a coverage that is in force from `effective` until the term ends
    (or until `cancelled_on`, if the policy was cancelled)."""
    tdays = term_days(term_start, term_end)
    if effective < term_start or effective >= term_end:
        raise PricingError("Effective date must fall within the policy term")
    end = term_end
    if cancelled_on is not None:
        if cancelled_on < term_start or cancelled_on > term_end:
            raise PricingError("Cancellation date must fall within the policy term")
        end = min(term_end, cancelled_on)
    covered = max(0, (end - effective).days)
    amount = round_div(term_premium_cents * covered, tdays)
    return Proration(
        term_premium_cents=term_premium_cents,
        term_days=tdays,
        effective_date=effective,
        end_date=end,
        covered_days=covered,
        amount_cents=amount,
    )


def format_usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"
