# Running SeatRush locally without Docker

This machine doesn't have Docker, so we run Postgres and Redis as native
Windows installs instead of containers. This is lighter on resources (no
WSL2/Hyper-V virtualization layer) and works exactly the same from the
app's point of view — it just talks to `localhost:5432` / `localhost:6379`.

## 1. PostgreSQL 16
1. Download the installer: https://www.postgresql.org/download/windows/
2. During setup, set the `postgres` superuser password (remember it) and keep the default port 5432.
3. After install, open **SQL Shell (psql)** (or `pgAdmin`) and run:
   ```sql
   CREATE USER seatrush WITH PASSWORD 'seatrush';
   CREATE DATABASE seatrush OWNER seatrush;
   ```
4. Confirm `DATABASE_URL` in `.env` matches: `postgresql+asyncpg://seatrush:seatrush@localhost:5432/seatrush`.

## 2. Redis
Redis has no official Windows build. **What this machine actually uses** is
a portable build extracted to `.tools/redis/` (gitignored), which needs no
install and no admin rights:

```powershell
# already downloaded; just start it (leave this window open)
.tools\redis\redis-server.exe --port 6379 --save "" --appendonly no
```
Confirm with `.tools\redis\redis-cli.exe ping` → `PONG`.

That portable build is Redis **5.0.14**. It predates the `HELLO` command
(Redis 6+), which `redis-py` uses to negotiate RESP3, so
`app/core/redis_client.py` pins `protocol=2`. That works against both this
build and the Redis 7 image in `docker-compose.yml`.

Alternatives if you'd rather have a real service: **Memurai**
(`choco install memurai-developer -y`, needs an elevated shell) or WSL1
running `redis-server`.

## 3. Python backend
```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# .env already present; otherwise: copy ..\.env.example .env
alembic upgrade head
python -m scripts.seed
uvicorn app.main:app --reload --port 8000
```

*Python version:* this was set up and tested on **Python 3.14**.
`requirements.txt` is pinned to releases that ship prebuilt wheels for
3.12–3.14. The original 2024-era pins (pydantic 2.9, asyncpg 0.29) had no
3.14 wheels and tried to compile pydantic-core from Rust, which fails
without a full toolchain — if you downgrade any pin, check wheel
availability for your interpreter first.

*Note on passwords:* the project uses `bcrypt` directly rather than
`passlib`, because passlib 1.7.4 is unmaintained and breaks against
bcrypt 5.x. Hashing is dispatched to a worker thread — see
`docs/bugs-found.md` #5 for why that matters.

## 4. Background workers (separate terminal)
```
cd backend
.venv\Scripts\Activate.ps1
python -m app.workers.run_workers
```

## 5. Frontend
```
cd frontend
npm install
npm run dev
```
Open http://localhost:3000.

## One-shot start
Once the above is set up once, `scripts/run-local.ps1` opens three terminals (API, workers, frontend) for you on subsequent runs.

## Running tests
```powershell
cd backend
.venv\Scripts\Activate.ps1
pytest -q          # 32 passed in ~39s
```
Tests need the same local Postgres and Redis running. They use a **separate
`seatrush_test` database** (create it once with
`CREATE DATABASE seatrush_test OWNER seatrush;`) and Redis DB index 1, so
your dev data is never touched. The schema is dropped and rebuilt at the
start of each run; the fixture refuses to run at all unless the target
database name ends in `_test`.
