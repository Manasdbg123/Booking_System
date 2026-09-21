from decimal import Decimal


def total_for_seats(seat_prices: list[Decimal]) -> Decimal:
    if not seat_prices:
        raise ValueError("A booking must include at least one seat")
    return sum(seat_prices, Decimal("0"))
