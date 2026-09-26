# Cancellation Policy

## Cancelling a HELD or PAYMENT_PENDING booking
A booking that has not yet been confirmed (status `HELD` or `PAYMENT_PENDING`)
can be cancelled by its owner at any time before the hold expires, at no
charge. Cancelling immediately releases the seats back to the show so other
customers can book them.

## Cancelling a CONFIRMED booking
A confirmed (paid) booking can be cancelled by its owner up until the show's
`starts_at` time. Cancelling a confirmed booking:
- Releases the seats back to FREE immediately.
- Does **not** automatically issue a refund through the AI assistant or the
  self-serve cancel endpoint. Refunds for confirmed bookings are processed by
  support within 5-7 business days once a refund request is filed, because
  the mock payment provider does not support instant reversal for
  already-settled charges.
- Cannot be undone. Once a confirmed booking is cancelled, the same seats
  must be re-booked from scratch (subject to availability) if the customer
  changes their mind.

## What cannot be cancelled
- A booking already in status `EXPIRED`, `FAILED`, or `CANCELLED` cannot be
  cancelled again (there is nothing left to release).
- Bookings for a show that has already started (`starts_at` in the past)
  cannot be cancelled through self-serve or the AI assistant; contact support.

## Who can cancel a booking
Only the user who owns the booking can cancel it. The AI assistant enforces
this the same way the REST API does: it always uses the authenticated
user's id to look up the booking and refuses to act on a booking owned by
someone else, regardless of what the user claims in chat.
