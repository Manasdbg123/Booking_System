# Architecture

```mermaid
flowchart LR
    subgraph Client
        FE["Next.js Frontend<br/>(App Router, TanStack Query, WebSocket)"]
    end

    subgraph API["FastAPI Backend"]
        Routers["Routers<br/>(auth, catalog, holds, bookings, payments,<br/>waitlist, queue, admin, realtime, health)"]
        Services["Services<br/>(hold, booking, waitlist, queue,<br/>idempotency, outbox, pricing)"]
        Repos["SQLAlchemy models / queries"]
    end

    subgraph Workers["Background Worker Process"]
        Expiry["Expiry sweep<br/>(holds, waitlist offers, queue admission)"]
        Outbox["Outbox drain<br/>(Postgres -> Redis pub/sub)"]
    end

    PG[("PostgreSQL 16<br/>source of truth")]
    Redis[("Redis 7<br/>rate limits, pub/sub, cache")]

    FE -- "HTTP (REST)" --> Routers
    FE -- "WebSocket" --> Routers
    Routers --> Services --> Repos --> PG
    Services -- "token bucket" --> Redis

    Expiry --> PG
    Outbox -- "reads unpublished events" --> PG
    Outbox -- "publish" --> Redis
    Redis -- "pub/sub" --> Routers
    Routers -- "forward to WS clients" --> FE
```

## Request lifecycle: booking a seat

```mermaid
sequenceDiagram
    participant U as User (browser)
    participant API as FastAPI
    participant DB as Postgres
    participant R as Redis
    participant W as Worker

    U->>API: POST /api/holds (Idempotency-Key, seat_ids)
    API->>DB: BEGIN; conditional UPDATE per seat (status='FREE'->'HELD')
    alt all seats acquired
        DB-->>API: success
        API->>DB: INSERT outbox_events(booking.held)
        API->>DB: COMMIT
        API-->>U: 201 Booking{status: HELD, expires_at}
    else any seat unavailable
        DB-->>API: 0 rows affected for that seat
        API->>DB: ROLLBACK
        API-->>U: 409 Conflict {unavailable seat_ids}
    end

    par outbox drain
        W->>DB: SELECT unpublished outbox_events
        W->>R: PUBLISH show:{id}:events
        R-->>API: pub/sub message
        API-->>U: WebSocket: seat now HELD
    end

    U->>API: POST /api/bookings/pay
    API->>DB: status HELD -> PAYMENT_PENDING
    API->>API: mock_payment_provider.charge() (async)
    Note over API: webhook arrives later (success/fail/timeout/duplicate)
    API->>DB: handle_webhook: lock booking FOR UPDATE, validate transition, confirm or fail
```

## Data model (entity overview)

```mermaid
erDiagram
    VENUE ||--o{ HALL : has
    HALL ||--o{ SECTION : has
    HALL ||--o{ SEAT : has
    SECTION ||--o{ SEAT : contains
    VENUE ||--o{ EVENT : hosts
    EVENT ||--o{ SHOW : has
    HALL ||--o{ SHOW : hosts
    SHOW ||--o{ SHOW_SEAT : "seat instances"
    SEAT ||--o{ SHOW_SEAT : instantiated_as
    USER ||--o{ BOOKING : makes
    SHOW ||--o{ BOOKING : for
    BOOKING ||--o{ BOOKING_SEAT : contains
    SHOW_SEAT ||--o| BOOKING_SEAT : claimed_by
    BOOKING ||--o{ PAYMENT : has
    USER ||--o{ WAITLIST_ENTRY : joins
    SHOW ||--o{ WAITLIST_ENTRY : for
    USER ||--o{ QUEUE_TICKET : holds
    SHOW ||--o{ QUEUE_TICKET : for
```
