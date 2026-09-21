-- Run after a k6 load test to verify the core guarantee: zero double-bookings.
-- psql -U seatrush -d seatrush -f k6/check-double-bookings.sql

-- 1. No show_seat should have more than one CONFIRMED booking_seats row.
SELECT show_seat_id, COUNT(*) AS confirmed_bookings
FROM booking_seats bs
JOIN bookings b ON b.id = bs.booking_id
WHERE b.status = 'CONFIRMED'
GROUP BY show_seat_id
HAVING COUNT(*) > 1;
-- Expect: 0 rows. Any row here is a double-booking bug.

-- 2. Invariant: every show_seat's status matches exactly one authoritative state.
SELECT ss.id, ss.status, COUNT(bs.id) AS confirmed_count
FROM show_seats ss
LEFT JOIN booking_seats bs ON bs.show_seat_id = ss.id
LEFT JOIN bookings b ON b.id = bs.booking_id AND b.status = 'CONFIRMED'
GROUP BY ss.id, ss.status
HAVING (ss.status = 'SOLD' AND COUNT(bs.id) FILTER (WHERE b.status = 'CONFIRMED') != 1)
    OR (ss.status != 'SOLD' AND COUNT(bs.id) FILTER (WHERE b.status = 'CONFIRMED') > 0);
-- Expect: 0 rows.
