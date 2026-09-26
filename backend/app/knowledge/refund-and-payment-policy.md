# Refund and Payment Policy

## How payment works
When you confirm a hold, SeatRush charges the total via a payment provider.
In this deployment the provider is a mock (`app/mock_payment_provider.py`)
that simulates success, failure, timeout, and duplicate-webhook delivery so
the booking state machine can be exercised realistically without a real
payment gateway. Every payment attempt is recorded with a unique
`provider_ref`, and every webhook delivery is idempotent: replaying the same
webhook twice never double-confirms a booking or double-charges a customer.

## When a refund happens automatically
The system automatically marks a payment `REFUNDED` (no customer action
needed) in these cases:
- The same payment webhook is somehow delivered as a duplicate charge on an
  already-confirmed booking (the extra charge is refunded).
- A payment succeeds *after* the seat hold already expired and the seats
  were re-sold to someone else in the meantime — the customer is charged
  nothing net; the attempted charge is refunded.
- A payment succeeds against a booking that is already `CANCELLED` or
  `FAILED` for any other reason.

## When a refund requires a support request
Cancelling a `CONFIRMED` booking yourself (self-serve or via the AI
assistant) releases your seats immediately but does not auto-refund the
charge already collected. File a refund request with support; refunds are
processed in 5-7 business days.

## Failed payments
If a payment fails (declined, timed out, or the provider reports failure),
the booking transitions to `FAILED` and the held seats are released
immediately so they don't sit unavailable. No charge is retained for a
failed payment attempt.
