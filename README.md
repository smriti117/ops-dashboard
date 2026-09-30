# Ops Dashboard — Backend

Django + Channels backend for the hospitality group ops dashboard. Handles transaction ingest from 40 POS venues and serves a live dashboard over WebSocket.

---

## Tech Stack

| Layer     | Technology                                               |
| --------- | -------------------------------------------------------- |
| Framework | Django 5.x + Django REST Framework                       |
| Real-time | Django Channels 4.x + Daphne (ASGI)                      |
| Database  | SQLite (dev) / PostgreSQL (production)                   |
| Auth      | DRF Token auth (ops users) + HMAC API key (POS machines) |

---

## Project Structure

```
backend/
├── config/
│   ├── settings.py       # All configuration, reads from .env
│   ├── urls.py           # HTTP routes
│   ├── asgi.py           # ASGI entry point — HTTP + WebSocket
│   └── routing.py        # (see dash/routing.py)
├── dash/
│   ├── models.py         # Venue, Transaction, VenueHourlyStats, VenueItemStats
│   ├── serializers.py    # Input validation for incoming POS transactions
│   ├── services.py       # All business logic — ingest, snapshot, alerts
│   ├── views.py          # HTTP endpoints (thin — delegates to services)
│   ├── consumers.py      # WebSocket consumer — pushes snapshot every 2s
│   ├── routing.py        # WebSocket URL routing
│   └── management/
│       └── commands/
│           ├── seed_demo.py      # Creates 40 venues + ops user
│           └── simulate_pos.py   # Fake POS traffic for development
├── .env                  # Local secrets (gitignored)
├── .env.example          # Template — copy to .env
└── requirements.txt
```

---

## Setup

### 1. Create and activate a virtual environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env if needed — defaults work for local development
```

### 4. Run migrations

```bash
python manage.py migrate
```

### 5. Seed demo data

Creates 40 venues and a default ops user (`ops` / `ops12345`):

```bash
python manage.py seed_demo
```

### 6. Start the server

```bash
python manage.py runserver
```

Daphne (ASGI) starts automatically because `daphne` is first in `INSTALLED_APPS`. The server handles both HTTP and WebSocket connections on `http://localhost:8000`.

---

## Simulating POS Traffic

In a separate terminal, run the POS simulator. It backfills 4 hours of history then streams live transactions:

```bash
source .venv/bin/activate
python manage.py simulate_pos
```

The simulator picks 2 random venues to go "quiet" (triggers sales drop alert) and 2 to go "hot" (triggers void/refund spike alert) so alerts are visible immediately.

Optional arguments:

```bash
python manage.py simulate_pos --url http://localhost:8000/api/transactions/ --interval 0.5
```

---

## Running Tests

```bash
python manage.py test dash --verbosity=2
```

Tests cover alert logic (pure function, no DB) and ingest idempotency.

---

## API Endpoints

### Authentication

All endpoints except `POST /api/transactions/` require a user token in the `Authorization` header.

**Get a token:**

```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "ops", "password": "ops12345"}'
# → {"token": "abc123..."}
```

---

### `POST /api/transactions/`

Ingest a transaction from a POS terminal. Authenticated by `X-API-Key` header (not user token).

**Headers:**

```
X-API-Key: dev-pos-key
Content-Type: application/json
```

**Request body:**

```json
{
  "venue_id": "V01",
  "transaction_id": "uuid-unique-per-transaction",
  "timestamp": "2024-01-15T14:32:00Z",
  "type": "sale",
  "items": [
    { "item_id": "P1", "name": "Lager pint", "qty": 2, "price": "9.50" }
  ],
  "total": "19.00",
  "staff_id": "S5"
}
```

- `type` must be one of `sale`, `void`, `refund`
- Duplicate `transaction_id` values are accepted but not double-counted (idempotent)
- Returns `201` on first ingest, `200` on duplicate

---

### `GET /api/dashboard/snapshot/`

Returns the current group-wide dashboard state. This is the same payload the WebSocket pushes every 2 seconds.

**Headers:** `Authorization: Token <token>`

**Response:**

```json
{
  "generated_at": "2024-01-15T14:32:05Z",
  "group_total": 18432.5,
  "venues": [
    {
      "code": "V03",
      "name": "Red Fox #3",
      "venue_type": "pub",
      "sales_today": 2140.0,
      "alerts": ["sales_drop"]
    }
  ],
  "top_items": [{ "item_name": "Lager pint", "qty": 312 }]
}
```

Venues are sorted highest to lowest net sales. Alerts are `sales_drop` and/or `void_spike`.

---

### `GET /api/venues/<code>/`

Returns hourly trade breakdown and top selling items for a single venue today.

**Headers:** `Authorization: Token <token>`

**Example:** `GET /api/venues/V03/`

**Response:**

```json
{
  "code": "V03",
  "name": "Red Fox #3",
  "hourly": [
    { "hour": "2024-01-15T09:00:00Z", "net_sales": 340.5, "transactions": 28 }
  ],
  "top_items": [{ "item_name": "Lager pint", "qty": 54 }]
}
```

---

### `WebSocket ws://localhost:8000/ws/dashboard/?token=<token>`

Live dashboard feed. Pushes a fresh snapshot (same shape as `GET /api/dashboard/snapshot/`) every 2 seconds.

Closes with code `4401` on invalid or missing token — clients should treat this as an auth failure, not a reconnectable error.

---

## Switching to PostgreSQL

Uncomment the Postgres block in `.env`:

```env
POSTGRES_DB=ops_dashboard
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-password
POSTGRES_HOST=localhost
```

Then run migrations:

```bash
python manage.py migrate
python manage.py seed_demo
```

No code changes required.

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Key variables:

| Variable      | Default              | Description                                  |
| ------------- | -------------------- | -------------------------------------------- |
| `SECRET_KEY`  | `dev-only-change-me` | Django secret key — **change in production** |
| `DEBUG`       | `1`                  | Set to `0` in production                     |
| `POS_API_KEY` | `dev-pos-key`        | Shared key for POS ingest endpoint           |
| `TIME_ZONE`   | `UTC`                | Defines when "today" resets for daily sales  |
| `POSTGRES_DB` | _(unset)_            | Set to enable PostgreSQL                     |

---

## Architecture Notes

**Write path:** `POST /api/transactions/` → validate → atomic DB write → update pre-aggregated stats tables using `F()` expressions (no lost updates under concurrent writes).

**Read path:** `build_snapshot()` reads only the small stats tables (~40 × 24 rows for hourly, one row per venue/date/item for items)never the raw transaction history. This keeps reads fast regardless of daily transaction volume.

**Alerts:** Computed as a pure function over a 4-hour sliding window. `sales_drop` fires when the last hour is below 50% of the hourly average of hours 1–4 ago. `void_spike` fires when (voids + refunds) exceed 15% of transactions, with a minimum volume guard.

**Idempotency:** `transaction_id` has a unique DB constraint. POS retries are safe — duplicates are detected and not re-counted.

---

## Decisions I've made on Backend Design & Features

**Pre-aggregate on write, not on read.**
The `VenueHourlyStats` and `VenueItemStats` tables are updated atomically every time a transaction arrives. The dashboard read path only touches those small derived tables never the raw transaction history. This keeps reads fast and predictable regardless of how many transactions accumulate during the day.

**`F()` expressions for stat increments.**
Increments like `sale_count += 1` are executed in SQL (`UPDATE ... SET sale_count = sale_count + 1`) rather than read-modify-write in Python. This eliminates lost updates when multiple venues POST concurrently.

**Idempotent ingest with a savepoint.**
The unique constraint on `transaction_id` makes the endpoint safe to retry. The duplicate detection uses a nested `atomic()` (savepoint) so a duplicate `IntegrityError` doesn't poison the outer transaction a Django-specific requirement when using Postgres.

**Two separate auth mechanisms.**
POS machines are automated systems they don't log in. A shared `X-API-Key` (with `hmac.compare_digest` to prevent timing attacks) is the right pattern for machine-to-machine auth. Human ops users get DRF token auth with per-user revocation.

---

## What I'd Improve With More Time

**Shared snapshot via Redis channel layer.**
Currently each connected browser tab runs its own set of DB queries every 2 seconds. With a Redis-backed channel layer, one background task builds the snapshot and fans it out to all connected clients same DB load regardless of how many people are watching.

**Refund item stats.**
Currently refunds reduce `sales_total` in `VenueHourlyStats` but do not reduce individual item `qty` in `VenueItemStats`. Matching refunded items back to their original sale lines would give accurate item-level numbers.

**Rate limiting on `/api/transactions/`.**
A misbehaving or buggy POS could flood the ingest endpoint. Request rate limiting (e.g. via `django-ratelimit`) would protect the DB.

**Pagination on venue and transaction endpoints.**
With more data historical transactions, larger venue lists the API endpoints would need cursor-based pagination. The snapshot endpoint currently returns all 40 venues in one payload; at larger scale this should be paginated or filtered by region. The raw transaction history endpoint (not yet exposed) would definitely need pagination before it could be used in any reporting feature.
