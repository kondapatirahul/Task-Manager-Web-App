"""Validation tests for administrator-managed task budget amounts."""
from decimal import Decimal

import pytest

from app.routes.tasks import parse_budget_amount


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, Decimal("0.00")),
        ("", Decimal("0.00")),
        ("12", Decimal("12.00")),
        ("12.345", Decimal("12.35")),
        ("0.01", Decimal("0.01")),
    ],
)
def test_parse_budget_amount_accepts_non_negative_values(raw, expected):
    amount, error = parse_budget_amount(raw, "Actual budget")
    assert error is None
    assert amount == expected


@pytest.mark.parametrize("raw", ["not-a-number", "NaN", "Infinity", "-0.01", "1000000000000"])
def test_parse_budget_amount_rejects_invalid_values(raw):
    amount, error = parse_budget_amount(raw, "Spent budget")
    assert amount is None
    assert error
