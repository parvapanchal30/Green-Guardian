# Local demo

A self-contained way to look at the product on your own computer. **It uses a throwaway SQLite file, never your Supabase
database, and needs no cloud account.** Nothing in it is real data.

## Run it
1. Double-click `demo.bat` in the repository root (or run it from a terminal). First run only: it installs the frontend packages
   (`npm ci`) if missing and builds the demo data (about 20 seconds).
2. It opens `http://localhost:5173`. The console prints three demo accounts with fresh random passwords (also saved in
   `backend/var/demo/DEMO_LOGIN.txt`) and asks whether to run the **automated tour** (below).
3. `tour.bat` replays the tour any time (`--manual` waits for Enter between steps, `--speed 2` is twice as fast, `--only agent,map`
   runs chosen steps). `demo.bat --fresh` throws the demo data away and rebuilds it. `demo-stop.bat` stops both servers.

## The two tours
- **Automated browser tour** (`tour.bat`, or `npm run tour` in `frontend/`): drives your installed Microsoft Edge or Chrome by
  itself through 17 steps (dashboard, lifecycle, corrections, agent, map, farm, harvests, roles, audit, datasets, protocols), signing
  in as owner, then worker, then viewer, with a caption on screen and the relevant part highlighted. It only looks: nothing is saved,
  so it can be repeated. Content is in `frontend/tour/steps.json`; `--screenshots <folder>` saves a PNG per step. It uses
  `playwright-core` (a development dependency; no browser is downloaded).
- **In-app tour**: the **Take the tour** button in the header of any workspace opens a step-by-step card (Back / Next / Close, Esc
  closes) that navigates the real pages of *your* workspace and highlights what it explains. Steps are generic (no demo names) and
  adapt to your role and the workspace mode (`frontend/src/tour/steps.ts`). It only navigates and highlights; it never saves.
  The two tours share the same step shape, so content can move between them; their wording differs (the automated one names the
  demo's assets).

Needs: Windows, Node 22+ and the backend virtual environment (`cd backend`, `python -m venv .venv`,
`.venv\Scripts\python.exe -m pip install -e ".[dev]"`).

## Run it by hand (what the script does)
```
cd backend
set DATABASE_URL=sqlite+pysqlite:///var/demo/demo.db
set JWT_SECRET=demo-only-local-secret-not-for-real-use-0123456789
set ENV=development
set WEATHER_PROVIDER=mock
set STORAGE_PROVIDER=local
set STORAGE_LOCAL_DIR=var/demo/storage
.venv\Scripts\python.exe -m app.tools.demo_seed
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000
```
then, in a second terminal: `cd frontend`, `npm run dev`, and open `http://localhost:5173`.

## What the demo contains
Created through the real API, so every rule, role and audit entry applied:
- **Riverside Campus Green Cover** (Green Management): 7 trees with observations, a declining Neem with a photo, an issue and
  tasks, a tree recorded dead (excluded from the active counts, map and agent), a heritage tree under monitoring, and the
  agent's rule-based suggestions.
- **Green Valley Farm** (Agricultural Production): four crop batches, harvests (one corrected by the owner), a failed batch, and
  the Yield and Harvest KPIs.
- Three accounts: owner (everything), worker (records, cannot decide or correct), viewer (read only).

The seed tool refuses to run unless `DATABASE_URL` is a local SQLite file with "demo" in its name.
