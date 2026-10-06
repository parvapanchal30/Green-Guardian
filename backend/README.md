# GreenGuardian backend

FastAPI + SQLAlchemy 2 + Alembic on hosted PostgreSQL/PostGIS. Architecture: `docs/ARCHITECTURE.md`. Database setup: `docs/DATABASE_SETUP.md`.

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Windows; use .venv/bin/pip on macOS/Linux
cp .env.example .env                        # then fill DATABASE_URL and JWT_SECRET (never commit .env)
.venv/Scripts/python -m alembic upgrade head
.venv/Scripts/python -m app.tools.check_db  # verifies PostgreSQL >= 15 and PostGIS
.venv/Scripts/python -m uvicorn app.main:create_app --factory --reload
```

Quality gates: `ruff check .` · `mypy app` · `pytest` (set `TEST_DATABASE_URL` to a disposable PostGIS database to also run the `postgis` tests; without it they are reported as skipped, i.e. NOT verified).

Run the rules-engine proof of concept: `python poc_run.py`.
