#!/usr/bin/env node
/**
 * The golden path, end to end in a real browser, in both modes (MVP exit criterion; ADR-082):
 *
 *   register → create a workspace → add a worker → register a plant → record declining observations →
 *   the agent suggests → accept (an issue opens) → plan a task for the worker → the worker completes it, recording the
 *   work and a follow-up check → resolve the issue as fixed → the check says the work helped, Today and the Analytics
 *   report count it
 *
 * It starts its own throwaway API (SQLite, made-up weather) and web app on spare ports, drives them with
 * playwright-core and an installed browser, and stops them again. It never touches a running demo or your database.
 *
 *   npm run e2e                     (Windows: uses Microsoft Edge and backend/.venv)
 *   E2E_BROWSER=chrome E2E_PYTHON=python npm run e2e     (CI on Linux)
 *   E2E_SHOW=1 npm run e2e          (watch it: a visible browser, slowed down)
 */
import { spawn, spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require('playwright-core')

const HERE = dirname(fileURLToPath(import.meta.url))
const FRONT = resolve(HERE, '..')
const BACK = resolve(FRONT, '..', 'backend')
const WIN = process.platform === 'win32'
const PY = process.env.E2E_PYTHON ?? join(BACK, '.venv', WIN ? 'Scripts/python.exe' : 'bin/python')
const API_PORT = Number(process.env.E2E_API_PORT ?? 8013)
const WEB_PORT = Number(process.env.E2E_WEB_PORT ?? 5183)
const BASE = `http://127.0.0.1:${WEB_PORT}`
const API = `http://127.0.0.1:${API_PORT}/api/v1`
const SHOW = process.env.E2E_SHOW === '1'
const ARTIFACTS = join(FRONT, 'e2e', 'artifacts')
const RUN = Date.now().toString(36)
const PASSWORD = 'Golden-Path-Test-Only-2026' // a throwaway account in a throwaway database

const children = []
const log = (msg) => console.log(`[golden-path] ${msg}`)

function stopAll() {
  for (const c of children.splice(0)) {
    if (c.exitCode !== null) continue
    if (WIN) spawnSync('taskkill', ['/pid', String(c.pid), '/T', '/F'], { stdio: 'ignore' })
    else try { process.kill(-c.pid, 'SIGTERM') } catch { /* already gone */ }
  }
}
process.on('exit', stopAll)
process.on('SIGINT', () => { stopAll(); process.exit(130) })

function start(cmd, args, opts) {
  const c = spawn(cmd, args, { ...opts, detached: !WIN, shell: false, stdio: ['ignore', 'pipe', 'pipe'] })
  let out = ''
  c.stdout.on('data', (d) => { out += d })
  c.stderr.on('data', (d) => { out += d })
  c.output = () => out.slice(-4000)
  children.push(c)
  return c
}

async function waitFor(url, what, ms = 90_000) {
  const until = Date.now() + ms
  while (Date.now() < until) {
    try { if ((await fetch(url)).status < 500) return } catch { /* not up yet */ }
    await new Promise((r) => setTimeout(r, 500))
  }
  throw new Error(`${what} did not start within ${ms / 1000} s`)
}

async function servers() {
  const dir = mkdtempSync(join(tmpdir(), 'gg-golden-'))
  const env = {
    ...process.env,
    DATABASE_URL: `sqlite+pysqlite:///${join(dir, 'golden.db').replace(/\\/g, '/')}`,
    JWT_SECRET: 'golden-path-test-only-secret-0123456789-abcdef',
    ENV: 'development',
    WEATHER_PROVIDER: 'mock',
    STORAGE_PROVIDER: 'local',
    STORAGE_LOCAL_DIR: join(dir, 'storage'),
  }
  log('migrating a fresh SQLite database')
  const mig = spawnSync(PY, ['-m', 'alembic', 'upgrade', 'head'], { cwd: BACK, env, encoding: 'utf8' })
  if (mig.status !== 0) throw new Error(`alembic failed:\n${mig.stdout}\n${mig.stderr}`)
  log(`starting the API on ${API_PORT}`)
  const api = start(PY, ['-m', 'uvicorn', 'app.main:create_app', '--factory', '--host', '127.0.0.1', '--port', String(API_PORT)], { cwd: BACK, env })
  await waitFor(`http://127.0.0.1:${API_PORT}/healthz`, 'the API').catch((e) => { throw new Error(`${e.message}\n${api.output()}`) })
  log(`starting the web app on ${WEB_PORT}`)
  const vite = join(FRONT, 'node_modules', 'vite', 'bin', 'vite.js')
  const web = start(process.execPath, [vite, '--port', String(WEB_PORT), '--strictPort', '--host', '127.0.0.1'], {
    cwd: FRONT, env: { ...process.env, VITE_DEV_API_TARGET: `http://127.0.0.1:${API_PORT}` },
  })
  await waitFor(`${BASE}/login`, 'the web app').catch((e) => { throw new Error(`${e.message}\n${web.output()}`) })
  return dir
}

async function registerByApi(name, email) {
  const r = await fetch(`${API}/auth/register`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name, email, password: PASSWORD }) })
  if (r.status !== 201) throw new Error(`could not register ${email}: ${r.status} ${await r.text()}`)
}

async function signIn(browser, email) {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 }, locale: 'en-GB' })
  const page = await ctx.newPage()
  await page.goto(`${BASE}/login`)
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'))
  return page
}

const expectText = async (locator, text, what) => {
  await locator.filter({ hasText: text }).first().waitFor({ timeout: 15_000 }).catch(() => { throw new Error(`expected ${what} to show "${text}"`) })
}

/** One mode, start to finish. */
async function goldenPath(browser, mode) {
  const agri = mode === 'agricultural_production'
  const tag = `${agri ? 'farm' : 'campus'}-${RUN}`
  const ownerEmail = `owner-${tag}@example.com`
  const workerEmail = `worker-${tag}@example.com`
  const plant = agri ? `Tomato block ${RUN}` : `Neem #${RUN}`
  const step = (s) => log(`${agri ? 'farm  ' : 'campus'} · ${s}`)

  // REGISTER (the owner through the sign-up page; the worker's account through the API, as if made elsewhere)
  step('owner registers and creates a workspace')
  const reg = await browser.newContext({ viewport: { width: 1360, height: 900 }, locale: 'en-GB' })
  let owner = await reg.newPage()
  await owner.goto(`${BASE}/register`)
  await owner.getByLabel('Name').fill(`Owner ${tag}`)
  await owner.getByLabel('Email').fill(ownerEmail)
  await owner.getByLabel(/Password/).first().fill(PASSWORD)
  await owner.getByRole('button', { name: 'Create account' }).click()
  await owner.getByRole('heading', { name: 'Your workspaces' }).waitFor()
  await owner.getByLabel('Workspace name').fill(agri ? `Golden Farm ${RUN}` : `Golden Campus ${RUN}`)
  await owner.getByRole('radio', { name: agri ? /Agricultural Production/ : /Green Management/ }).check()
  await owner.getByRole('button', { name: 'Create workspace' }).click()
  await owner.waitForURL(/\/w\/[^/]+\/?$/)
  const ws = new URL(owner.url()).pathname.split('/')[2]
  await registerByApi(`Worker ${tag}`, workerEmail)

  step('owner adds the worker')
  await owner.goto(`${BASE}/w/${ws}/settings/members`)
  await owner.getByRole('button', { name: 'Add a member' }).click()
  const add = owner.getByRole('form', { name: 'Add a member' })
  await add.getByLabel('Email').fill(workerEmail)
  await add.getByLabel('Role').selectOption('worker')
  await add.getByRole('button', { name: 'Add', exact: true }).click()
  await expectText(owner.getByRole('table', { name: 'Workspace members' }).getByRole('row'), workerEmail, 'the members table')

  // REGISTER A PLANT
  step(`owner registers ${plant}`)
  await owner.goto(`${BASE}/w/${ws}/assets`)
  await owner.getByRole('button', { name: 'Register asset' }).first().click()
  const form = owner.getByRole('form', { name: 'Register asset' })
  await form.getByLabel(/Name \/ identifier/).fill(plant)
  if (agri) await form.getByLabel('Estimated plants').fill('1200')
  await form.getByRole('button', { name: 'Register asset' }).click()
  await owner.waitForURL(/\/assets\/[0-9a-f-]{36}/)
  const assetUrl = owner.url()

  // OBSERVE: healthy first, then declining to critical
  for (const score of ['82', '31']) {
    step(`owner records health ${score}`)
    await owner.getByRole('button', { name: 'Record', exact: true }).first().click()
    const sheet = owner.getByRole('dialog')
    await sheet.getByLabel(/Health score/).fill(score)
    await sheet.getByRole('button', { name: 'Save observation' }).click()
    await sheet.waitFor({ state: 'detached' })
  }

  // DETECT → the agent suggests; ACCEPT → an issue opens
  step('the agent suggests; the owner accepts')
  await owner.goto(`${BASE}/w/${ws}`)
  const accept = owner.getByRole('button', { name: 'Accept: open issue' })
  const suggestion = owner.getByRole('listitem').filter({ hasText: `${plant} health is critical (31)` }).filter({ has: accept })
  await suggestion.waitFor({ timeout: 20_000 }).catch(() => { throw new Error('no "health is critical" suggestion appeared on Today') })
  await suggestion.getByRole('button', { name: 'Accept: open issue' }).click()
  await accept.waitFor({ state: 'detached', timeout: 15_000 })
  await owner.goto(`${BASE}/w/${ws}/issues`)
  await owner.getByRole('link', { name: new RegExp(plant.replace(/[#]/g, '.')) }).first().click()
  await owner.waitForURL(/\/issues\/[0-9a-f-]{36}/)
  const issueUrl = owner.url()

  // PLAN → a task for the worker
  step('owner plans a treatment task for the worker')
  await owner.getByRole('button', { name: 'Add task' }).click()
  const task = owner.getByRole('form', { name: 'Add task' })
  await task.getByLabel('Task').fill(`Treat ${plant}`)
  await task.getByLabel('Type').selectOption('treat')
  await task.getByLabel('Assign to').selectOption({ label: `Worker ${tag} (Worker)` })
  await task.getByRole('button', { name: 'Create task' }).click()
  await expectText(owner.getByRole('region', { name: 'Tasks' }).getByRole('listitem'), `Treat ${plant}`, 'the issue\'s tasks')

  // ACT → the worker completes the task, recording the work and a follow-up check
  step('worker completes the task with the work done and a follow-up score')
  const worker = await signIn(browser, workerEmail)
  await worker.goto(`${BASE}/w/${ws}/tasks`)
  const row = worker.getByRole('listitem').filter({ hasText: `Treat ${plant}` })
  await row.getByRole('button', { name: 'Complete' }).click()
  const done = worker.getByRole('form', { name: /Complete T-/ })
  await done.getByLabel('What was done?').fill('Copper spray on the affected canopy')
  await done.getByLabel(/Health score now/).fill('78')
  await done.getByRole('button', { name: 'Mark done' }).click()
  await done.waitFor({ state: 'detached', timeout: 15_000 })

  // RESOLVE → fixed, which the follow-up check allows
  step('owner resolves the issue as fixed')
  await owner.goto(issueUrl)
  await owner.getByRole('heading', { name: /did the work help/i }).filter({ hasText: 'Improved' }).waitFor({ timeout: 15_000 })
    .catch(() => { throw new Error('the issue page does not say the work helped (Improved)') })
  await owner.getByRole('button', { name: /^Resolve/ }).first().click()
  await owner.getByLabel('Outcome').selectOption('fixed')
  await owner.getByLabel('Resolution notes').fill('Recovered after the treatment')
  await owner.getByRole('button', { name: 'Confirm' }).click()
  await expectText(owner.locator('p'), 'Recovered after the treatment', 'the closed issue')

  // THE RECORD REFLECTS IT: the plant, Today and the report
  step('the plant, Today and the Analytics report reflect it')
  await owner.goto(assetUrl)
  await expectText(owner.locator('body'), 'Healthy · 78', 'the plant page')
  await owner.goto(`${BASE}/w/${ws}`)
  await expectText(owner.locator('p'), '1 healthy, 0 at risk and 0 critical', 'the Today summary')
  await expectText(owner.locator('p'), '0 issues are open', 'the Today summary')
  await owner.goto(`${BASE}/w/${ws}/reports/analytics`)
  await expectText(owner.getByRole('region', { name: 'Summary' }), 'Issues: 1 opened, 1 closed, 0 still open.', 'the Analytics summary')
  await expectText(owner.getByRole('region', { name: 'Summary' }), '1 of 1 tasks created were completed', 'the Analytics summary')
  await worker.context().close()
  await reg.close()
  step('passed')
}

let failed = false
let browser
const dir = await servers().catch((e) => { console.error(e.message); stopAll(); process.exit(1) })
try {
  browser = await chromium.launch({ channel: process.env.E2E_BROWSER ?? (WIN ? 'msedge' : 'chrome'), headless: !SHOW, slowMo: SHOW ? 250 : 0 })
  for (const mode of ['green_management', 'agricultural_production']) {
    try {
      await goldenPath(browser, mode)
    } catch (e) {
      failed = true
      console.error(`[golden-path] FAILED in ${mode}: ${e.message}`)
      mkdirSync(ARTIFACTS, { recursive: true })
      for (const ctx of browser.contexts()) for (const [i, p] of ctx.pages().entries()) {
        await p.screenshot({ path: join(ARTIFACTS, `${mode}-${i}.png`), fullPage: true }).catch(() => {})
      }
      for (const ctx of browser.contexts()) await ctx.close().catch(() => {})
    }
  }
} finally {
  await browser?.close().catch(() => {})
  stopAll()
  try { rmSync(dir, { recursive: true, force: true }) } catch { /* Windows may still hold the file briefly */ }
}
log(failed ? 'FAILED (screenshots in frontend/e2e/artifacts)' : 'both modes passed')
process.exit(failed ? 1 : 0)
