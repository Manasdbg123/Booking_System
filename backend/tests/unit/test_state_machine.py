import pytest

from app.models import BookingStatus
from app.services.booking_service import InvalidTransitionError, _assert_transition


@pytest.mark.parametrize(
    "current,target",
    [
        (BookingStatus.HELD, BookingStatus.PAYMENT_PENDING),
        (BookingStatus.HELD, BookingStatus.EXPIRED),
        (BookingStatus.HELD, BookingStatus.CANCELLED),
        (BookingStatus.PAYMENT_PENDING, BookingStatus.CONFIRMED),
        (BookingStatus.PAYMENT_PENDING, BookingStatus.FAILED),
        (BookingStatus.PAYMENT_PENDING, BookingStatus.EXPIRED),
        (BookingStatus.EXPIRED, BookingStatus.CONFIRMED),
    ],
)
def test_valid_transitions_allowed(current, target):
    _assert_transition(current, target)  # should not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (BookingStatus.CONFIRMED, BookingStatus.HELD),
        (BookingStatus.CANCELLED, BookingStatus.CONFIRMED),
        (BookingStatus.FAILED, BookingStatus.CONFIRMED),
        (BookingStatus.HELD, BookingStatus.CONFIRMED),  # must go through PAYMENT_PENDING
        (BookingStatus.EXPIRED, BookingStatus.PAYMENT_PENDING),
        (BookingStatus.CONFIRMED, BookingStatus.HELD),
    ],
)
def test_invalid_transitions_rejected(current, target):
    with pytest.raises(InvalidTransitionError):
        _assert_transition(current, target)
