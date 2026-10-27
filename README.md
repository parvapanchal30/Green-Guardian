# GreenGuardian

An operating system for biological assets: trees, plants, crop batches, fields and parks, followed through their whole
life. Register what exists, record what you see, notice what is going wrong, turn it into issues and tasks, record the
work, check whether it helped, and get rule-based suggestions for what to do next.

One product, two modes over the same records:

- **Green Management** (campuses, parks, NGOs, municipalities): survival, health, growth, canopy, coverage.
- **Agricultural Production** (farms, orchards, growers): growth, health, yield, harvest.

A personal and college major project, non-commercial (see ADR-065 in `docs/DECISION_LOG.md`).

## What it does today

- **Plants and places**: register trees, plants and crop batches with species, location, tag and stage; fields, zones and
  sites; a species catalog; a lifecycle with stages and exits (dead, failed, removed).
- **Observing**: health scores, symptoms, measurements and photos from one Record sheet, on desktop or phone.
- **Issues and tasks**: issues with severity, evidence and a workflow; tasks with due dates, roles and history; recorded
  work (treatments, watering) and a follow-up check of whether it helped; recurring inspections.
- **Operations agent**: fixed rules over the records (critical health, falling health, plants nobody has looked at,
  rain ahead of watering) that suggest; a person decides. No machine learning or language model is used.
- **Monitoring**: today's summary, health and growth over time, a map, and weather from Open-Meteo for your places or any
  place you search or pin.
- **Reports**: Analytics and Impact for a chosen period, computed from the records, with print and CSV.
- **Teams**: workspaces with owner, admin, manager, worker and viewer roles, member management, and a read-only audit log.
- **English and Hindi** throughout; light and dark themes.

Everything the app shows is labelled for what it is (rule, statistical, forecast); planned features such as disease
detection or yield prediction are listed under "Coming next" and are not faked.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL with PostGIS (SQLite for tests and the local demo).
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Query, Leaflet.
- **Design**: the "Field Ledger" design system (`docs/DESIGN_SYSTEM.md`): Zilla Slab, Hind and JetBrains Mono, Lucide icons.

## Try it locally (Windows)

The quickest way is the local demo: a throwaway SQLite database with example workspaces, real weather and a background
worker. It never touches a real database.

```bat
demo.bat
```

It opens http://localhost:5173. The demo accounts and the tours are described in `docs/DEMO.md`; `demo-stop.bat` stops it.

First-time setup it needs: Node 22+ and the backend environment:

```bat
cd backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Develop against your own database

```bat
cd backend
copy .env.example .env
rem fill in DATABASE_URL and JWT_SECRET in .env (never commit it)
.venv\Scripts\python -m alembic upgrade head
.venv\Scripts\python -m uvicorn app.main:create_app --factory --reload --port 8000
```

In a second terminal:

```bat
cd frontend
npm ci
npm run dev
```

Optional scheduled agent runs: `cd backend` then `.venv\Scripts\python -m app.worker`.

## Checks

```bat
cd backend
.venv\Scripts\python -m ruff check app tests
.venv\Scripts\python -m pytest -q

cd frontend
npx tsc -b
npm run lint
npx vitest run
npm run build
npm run e2e
```

`npm run e2e` is the golden path in a real browser, in both modes: it starts its own throwaway API and web app,
registers a plant, records declining health, accepts the agent's suggestion, has a worker complete the task with a
follow-up check, resolves the issue and checks that Today and the Analytics report reflect it (Microsoft Edge on
Windows, Google Chrome on Linux).

Backend tests run against SQLite by default; set `TEST_DATABASE_URL` to a disposable PostgreSQL database to run them on
PostgreSQL too (`docs/DATABASE_SETUP.md`). Every workspace endpoint is covered by a tenant-isolation test.

## Repository

| Path | What is there |
|---|---|
| `backend/` | API, domain modules (`app/modules/*`), migrations, worker, tests |
| `frontend/` | Web app (`src/pages`, `src/components`, `src/i18n`), tests, automated tour |
| `docs/` | Product, architecture, domain model, API, decisions and current state |
| `docker/`, `ops/` | Container setup, backup and restore scripts |
| `pitch/` | Presentation material |

## Read next

1. `docs/PRODUCT_VISION.md`: what GreenGuardian is and is not
2. `docs/CURRENT_STATE.md`: what is built and how it was verified
3. `docs/TODO.md`: what comes next
4. `docs/ARCHITECTURE.md`, `docs/DOMAIN_MODEL.md`, `docs/API_SPECIFICATION.md`
5. `docs/DECISION_LOG.md`: every architectural and product decision, with its reasons

## Data and attribution

Weather and place search by [Open-Meteo](https://open-meteo.com) (CC BY 4.0). Map data © OpenStreetMap contributors.
Fonts under the SIL Open Font License; icons by Lucide (ISC).
