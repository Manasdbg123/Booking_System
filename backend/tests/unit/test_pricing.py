from decimal import Decimal

import pytest

from app.services import pricing


def test_total_for_seats_sums_prices():
    assert pricing.total_for_seats([Decimal("100"), Decimal("250.50")]) == Decimal("350.50")


def test_total_for_seats_single_seat():
    assert pricing.total_for_seats([Decimal("999.99")]) == Decimal("999.99")


def test_total_for_seats_rejects_empty():
    with pytest.raises(ValueError):
        pricing.total_for_seats([])
