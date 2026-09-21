from prometheus_client import Counter, Gauge, Histogram

hold_latency_seconds = Histogram("seatrush_hold_latency_seconds", "Latency of seat hold requests")
hold_conflicts_total = Counter("seatrush_hold_conflicts_total", "Number of hold attempts that lost a race for a seat")
holds_created_total = Counter("seatrush_holds_created_total", "Number of successful holds created")
holds_expired_total = Counter("seatrush_holds_expired_total", "Number of holds that expired and were released")
bookings_confirmed_total = Counter("seatrush_bookings_confirmed_total", "Number of confirmed bookings")
bookings_failed_total = Counter("seatrush_bookings_failed_total", "Number of failed/expired bookings")
queue_depth = Gauge("seatrush_queue_depth", "Current waiting-room queue depth", ["show_id"])
waitlist_depth = Gauge("seatrush_waitlist_depth", "Current waitlist depth", ["show_id", "section_id"])
outbox_backlog = Gauge("seatrush_outbox_backlog", "Number of unpublished outbox events")
