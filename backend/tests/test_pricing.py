from datetime import date

import pytest

from app.pricing import PricingError, format_usd, prorate, round_div, term_days, term_premium

START = date(2026, 1, 1)
END = date(2027, 1, 1)  # exclusive: 365 days


def test_term_is_365_days():
    assert term_days(START, END) == 365


def test_full_term_premium_equals_annual_price_for_365_day_term():
    assert term_premium("tech_eo", "1M", START, END) == 365_000
    assert term_premium("general_liability", "1M", START, END) == 240_000


def test_unknown_coverage_rejected():
    with pytest.raises(PricingError):
        term_premium("nope", "1M", START, END)
    with pytest.raises(PricingError):
        term_premium("cyber", "9M", START, END)


def test_round_half_up():
    assert round_div(1, 2) == 1  # 0.5 -> 1
    assert round_div(1, 3) == 0
    assert round_div(2, 3) == 1
    assert round_div(5, 10) == 1


def test_worked_example_original_date():
    # $3,650/yr rider = $10.00/day; effective Mar 1 -> 306 days -> $3,060.00
    p = prorate(365_000, START, END, date(2026, 3, 1))
    assert p.covered_days == 306
    assert p.amount_cents == 306_000


def test_worked_example_corrected_date_is_70_dollars_more():
    # Corrected to Feb 22 -> 313 days -> $3,130.00 (a week earlier = 7 more days = +$70)
    original = prorate(365_000, START, END, date(2026, 3, 1))
    corrected = prorate(365_000, START, END, date(2026, 2, 22))
    assert corrected.covered_days == 313
    assert corrected.amount_cents == 313_000
    assert corrected.amount_cents - original.amount_cents == 7_000


def test_full_term_coverage_from_start_day_is_full_premium():
    assert prorate(240_000, START, END, START).amount_cents == 240_000


def test_last_day_of_term_is_one_day():
    p = prorate(365_000, START, END, date(2026, 12, 31))
    assert p.covered_days == 1
    assert p.amount_cents == 1_000


def test_effective_date_outside_term_rejected():
    with pytest.raises(PricingError):
        prorate(365_000, START, END, date(2025, 12, 31))
    with pytest.raises(PricingError):
        prorate(365_000, START, END, END)


def test_cancellation_pro_rata_base():
    # Cancel effective Jul 1: 181 days earned, 184 unearned.
    earned = prorate(240_000, START, END, START, cancelled_on=date(2026, 7, 1))
    assert earned.covered_days == 181
    assert earned.amount_cents == round_div(240_000 * 181, 365)  # 119,014 -> $1,190.14
    assert 240_000 - earned.amount_cents == 120_986  # $1,209.86 unearned


def test_cancellation_before_effective_date_earns_nothing():
    p = prorate(365_000, START, END, date(2026, 6, 1), cancelled_on=date(2026, 3, 1))
    assert p.covered_days == 0
    assert p.amount_cents == 0


def test_cancellation_on_start_date_earns_nothing():
    assert prorate(240_000, START, END, START, cancelled_on=START).amount_cents == 0


def test_cancellation_outside_term_rejected():
    with pytest.raises(PricingError):
        prorate(240_000, START, END, START, cancelled_on=date(2027, 2, 1))


def test_non_standard_term_scales_annual_price():
    # 182-day term: 365,000 * 182 / 365 = 182,000
    assert term_premium("tech_eo", "1M", date(2026, 1, 1), date(2026, 7, 2)) == 182_000


def test_format_usd():
    assert format_usd(306_000) == "$3,060.00"
    assert format_usd(-7_005) == "-$70.05"
    assert format_usd(0) == "$0.00"
