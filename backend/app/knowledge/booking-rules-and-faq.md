# Booking Rules and FAQ

## Seat holds
Selecting seats places a **hold**, not a booking. A hold reserves the seats
for you for a limited time (see `hold_ttl_seconds` in configuration, default
5 minutes). If you don't complete payment within that window, the hold
expires automatically and the seats become available to other customers
again. You can re-hold the same seats afterward if they're still free.

## Multi-seat holds
You can hold up to 10 seats in a single request. Either all requested seats
are held, or none are — SeatRush never partially holds a multi-seat request,
so you won't end up with 3 of the 4 seats you asked for.

## Idempotency
Every hold, payment, and cancellation request supports an `Idempotency-Key`
header. If a request is retried (e.g. due to a network blip) with the same
key, SeatRush returns the original result instead of creating a duplicate
booking or charge.

## Waitlist
If a show's seats are sold out in a section you want, you can join that
section's waitlist. When a seat frees up (expiry, cancellation, or failed
payment), it is offered to the next person in line, first-in-first-out, with
a limited time to claim it before it moves to the next person.

## Waiting room
For very high-demand ("hot") shows, SeatRush places customers in a virtual
waiting room and admits them in controlled batches, so the booking flow
doesn't collapse under a traffic spike. You need an admission token from the
waiting room before your hold request is accepted for a hot show.

## Ticket codes
A confirmed booking gets a unique ticket code. This is your proof of
booking; you do not need to print anything, it's looked up by booking id in
"My Bookings".

## What the AI assistant can and cannot do
The assistant can search shows, check seat availability and pricing,
recommend options, look up and cancel your own bookings, and place a hold
for you to confirm. It cannot pay on your behalf without you explicitly
confirming the purchase in chat, cannot see or touch another user's
bookings, and cannot bypass any of the rules above.
