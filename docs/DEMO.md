# Local demo

A self-contained way to look at the product on your own computer. **It uses a throwaway SQLite file, never your Supabase
database, and needs no cloud account.** The plants and records are examples, but the product runs live on them: every
figure is computed from the records, the **weather is the real Open-Meteo forecast** for the demo plants' coordinates (Mumbai
and Pune), and a **background worker** runs the scheduled agent checks and recurring inspections, as in production.

## Run it
1. Double-click `demo.bat` in the repository root (or run it from a terminal). First run only: it installs the frontend packages
   (`npm ci`) if missing and builds the demo data (about 20 seconds).
2. It opens `http://localhost:5173`; sign in with one of the demo accounts below (also printed in the console and saved in
   `backend/var/demo/DEMO_LOGIN.txt`). It asks whether to run the **automated tour** (below).
3. `tour.bat` replays the tour any time (`--manual` waits for Enter between steps, `--speed 2` is twice as fast, `--only agent,map`
   runs chosen steps). `demo.bat --fresh` throws the demo data away and rebuilds it. On every start an existing demo database is brought up to date (`alembic upgrade head`: new tables only, the data is kept); demo data added for newer features, such as the recorded work on Neem #102, only appears after `--fresh`. `demo.bat --offline` uses made-up weather (the demo also falls back to it by itself when Open-Meteo cannot be reached;
   the console says which it used). `demo-stop.bat` stops the demo's API, web app and worker, and nothing you started yourself.

## Demo accounts
These exist **only in the local demo database** (`backend/var/demo/demo.db`). The passwords are fixed so these instructions stay
true after `demo.bat --fresh`; they are not secrets, protect nothing real, and must never be used for a real account. Your
browser may offer passwords saved for other local accounts (for example from the Supabase development database): ignore those.

| Role | Email | Password | Can do |
|---|---|---|---|
| Owner | `demo.owner@example.com` | `GreenDemo-Owner-2026` | everything, in both workspaces |
| Worker | `demo.worker@example.com` | `GreenDemo-Worker-2026` | record observations, work and harvests; cannot decide, correct or close |
| Viewer | `demo.viewer@example.com` | `GreenDemo-Viewer-2026` | read only, campus workspace |

Workspaces: **Riverside Campus Green Cover** (Green Management) and **Green Valley Farm** (Agricultural Production). Things to
look at: issue *Neem #102 crown dieback* (work recorded, "Did the work help?" awaiting a check, a follow-up inspection task),
the lifecycle of *Gulmohar #09* (dead) and *Okra block C* (failed), the corrected harvest of *Tomato block A*, and growth measurements of *Neem #101*, *Mango #07*, the sapling and *Wheat field 3* (Growth page and KPI), the monthly **recurring inspection** of *Banyan #01* (its first task already exists). Recurring tasks are created by the demo's background worker when they fall due, when a schedule is saved, or by **Create due tasks now**. The worker runs the agent once a day per workspace, so a fresh demo (whose build already ran it) shows its first scheduled run the next day.
A demo database built before 2026-10-25 still has the old random passwords (see its `DEMO_LOGIN.txt`) until `demo.bat --fresh`.

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

## Running it in VS Code
Open the repository folder, then open two terminals (Terminal → New Terminal, then the split button).

- **Against the local demo data** (Command Prompt; in PowerShell write `$env:NAME="value"` instead of `set NAME=value`): in
  terminal 1 run the commands under *Run it by hand* below; in terminal 2 run `cd frontend` and `npm run dev`; open
  `http://localhost:5173`.
- **Against your development database** (the settings in `backend\.env`): terminal 1, `cd backend`,
  `.venv\Scripts\python -m alembic upgrade head`, `.venv\Scripts\python -m uvicorn app.main:create_app --factory --reload
  --port 8000`; terminal 2 as above. The demo accounts do not exist there; register your own. Optional third terminal for
  scheduled agent runs: `cd backend`, `.venv\Scripts\python -m app.worker`.
- Tests: `cd backend` then `.venv\Scripts\python -m pytest -q` (fast SQLite mode); `cd frontend` then `npx vitest run`.
- Stop a server with Ctrl+C in its terminal (or `demo-stop.bat`).

## Example data in your development database
The demo accounts exist only in the local demo file. To get the same example content in the database `backend\.env`
points at (your Supabase development database), under **your own** account:

1. Start the app against that database and **register** on the sign-in page (any email; 10+ character password).
2. In a terminal: `cd backend`, then `.venv\Scripts\python -m app.tools.example_data --email you@example.com`
   (the email you registered with). It shows the database host it will write to and asks you to type `yes`.
3. Sign in as yourself: "Riverside Campus Green Cover (example)" and "Green Valley Farm (example)" are yours (owner).

It creates no other accounts and needs no password (it signs in as you on the server). The field work is recorded under
your name. It runs once per account, refuses production, and deletes nothing. With real weather configured
(`WEATHER_PROVIDER=open_meteo`), the agent's irrigation advice for these examples uses the real forecast for their
coordinates.

## Run it by hand (what the script does)
```
cd backend
set DATABASE_URL=sqlite+pysqlite:///var/demo/demo.db
set JWT_SECRET=demo-only-local-secret-not-for-real-use-0123456789
set ENV=development
set WEATHER_PROVIDER=open_meteo   (or mock, offline)
set STORAGE_PROVIDER=local
set STORAGE_LOCAL_DIR=var/demo/storage
.venv\Scripts\python.exe -m app.tools.demo_seed
.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --port 8000
```
then, in a second terminal: `cd frontend`, `npm run dev`, and open `http://localhost:5173`; optionally, in a third terminal with
the same settings, `.venv\Scripts\python.exe -m app.worker` for the scheduled checks.

## What the demo contains
Created through the real API, so every rule, role and audit entry applied:
- **Riverside Campus Green Cover** (Green Management): 7 trees with observations, a declining Neem with a photo, an issue and
  tasks, a tree recorded dead (excluded from the active counts, map and agent), a heritage tree under monitoring, and the
  agent's rule-based suggestions.
- **Green Valley Farm** (Agricultural Production): four crop batches, harvests (one corrected by the owner), a failed batch, and
  the Yield and Harvest KPIs.
- Three accounts: owner (everything), worker (records, cannot decide or correct), viewer (read only).

The seed tool refuses to run unless `DATABASE_URL` is a local SQLite file with "demo" in its name.
