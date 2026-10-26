// Automated browser tour of the local GreenGuardian demo.
//
//   npm run tour                 # from frontend/: runs the whole tour on its own, slowly, with on-screen captions
//   npm run tour -- --manual     # waits for Enter between steps instead of advancing by itself
//   npm run tour -- --speed 2    # twice as fast (0.5 = half speed)
//   npm run tour -- --only agent,map     # just those steps (ids are in steps.json)
//   npm run tour -- --keep-open  # leave the browser open at the end
//   npm run tour -- --screenshots <folder>   # also save one PNG per step (useful for checking and for documentation)
//
// It drives YOUR installed Microsoft Edge or Chrome (no browser is downloaded) against the demo started by demo.bat,
// signing in with the throwaway demo accounts from backend/var/demo/DEMO_LOGIN.txt. It only looks: it never saves anything,
// so it can be run again and again. The content of every step lives in steps.json.
import { readFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import readline from 'node:readline/promises'
import { chromium } from 'playwright-core'

const here = dirname(fileURLToPath(import.meta.url))
const args = process.argv.slice(2)
const flag = (name) => args.includes(`--${name}`)
const value = (name, fallback) => {
  const i = args.indexOf(`--${name}`)
  return i >= 0 && args[i + 1] ? args[i + 1] : fallback
}
const BASE = value('base', 'http://localhost:5173')
const SPEED = Number(value('speed', '1')) || 1
const ONLY = value('only', '') ? value('only', '').split(',') : null
const MANUAL = flag('manual')
const SHOTS = value('screenshots', '')
if (SHOTS) mkdirSync(SHOTS, { recursive: true })
const tour = JSON.parse(readFileSync(join(here, 'steps.json'), 'utf8'))
const steps = tour.steps.filter((s) => !ONLY || ONLY.includes(s.id))

// ------------------------------------------------------------------------------------------------ demo accounts
function demoAccounts() {
  const file = join(here, '..', '..', 'backend', 'var', 'demo', 'DEMO_LOGIN.txt')
  if (!existsSync(file)) throw new Error(`Demo accounts not found (${file}). Start the demo with demo.bat first.`)
  const accounts = {}
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^(Owner|Worker|Viewer)\s+(\S+)\s+(\S+)/)
    if (m) accounts[m[1].toLowerCase()] = { email: m[2], password: m[3] }
  }
  for (const who of ['owner', 'worker', 'viewer']) if (!accounts[who]) throw new Error(`No ${who} account in DEMO_LOGIN.txt`)
  return accounts
}

// ------------------------------------------------------------------------------------------------ on-screen caption
async function caption(page, { n, total, who, title, text }) {
  await page.evaluate(
    ({ n, total, who, title, text }) => {
      let box = document.getElementById('gg-tour')
      if (!box) {
        box = document.createElement('div')
        box.id = 'gg-tour'
        box.setAttribute('role', 'status')
        Object.assign(box.style, {
          position: 'fixed', left: '50%', bottom: '18px', transform: 'translateX(-50%)', zIndex: '2147483647',
          width: 'min(760px, calc(100vw - 32px))', background: 'rgba(20, 31, 24, 0.94)', color: '#fff', borderRadius: '10px',
          padding: '14px 18px', font: '15px/1.45 system-ui, sans-serif', boxShadow: '0 8px 30px rgba(0,0,0,.35)', pointerEvents: 'none',
        })
        document.body.appendChild(box)
      }
      box.replaceChildren()
      const meta = document.createElement('div')
      meta.textContent = `Step ${n} of ${total}  ·  signed in as ${who}`
      Object.assign(meta.style, { fontSize: '12px', opacity: '.7', marginBottom: '4px' })
      const h = document.createElement('div')
      h.textContent = title
      Object.assign(h.style, { fontWeight: '700', fontSize: '17px', marginBottom: '4px' })
      const p = document.createElement('div')
      p.textContent = text
      box.append(meta, h, p)
    },
    { n, total, who, title, text },
  )
}

async function highlight(page, selector) {
  await page.evaluate(() => {
    for (const el of document.querySelectorAll('[data-gg-focus]')) {
      el.style.outline = ''
      el.style.outlineOffset = ''
      el.removeAttribute('data-gg-focus')
    }
  })
  if (!selector) return
  const target = page.locator(selector).first()
  await target.waitFor({ state: 'visible', timeout: 8000 })
  await target.evaluate((el) => {
    el.scrollIntoView({ block: 'start' })
    window.scrollBy(0, -28) // keep the top of the section clear of the edge; the caption sits at the bottom
  })
  await target.evaluate((el) => {
    el.setAttribute('data-gg-focus', '1')
    el.style.outline = '3px solid #f59e0b'
    el.style.outlineOffset = '4px'
  })
}

// ------------------------------------------------------------------------------------------------ driving the app
async function signIn(page, account) {
  await page.goto(`${BASE}/login`)
  await page.getByLabel('Email').fill(account.email)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 15000 })
}

async function signOut(page) {
  // Sign out lives in the account menu (ADR-069): open it first when it is there.
  const account = page.getByRole('button', { name: /^Account:/ })
  if (await account.count()) await account.first().click()
  const button = page.getByRole('button', { name: 'Sign out' })
  if (await button.count()) await button.first().click()
  else await page.goto(`${BASE}/login`)
  await page.waitForURL(/\/login/, { timeout: 10000 })
}

async function workspaceIds(page) {
  await page.goto(`${BASE}/`)
  const ids = {}
  for (const [key, name] of [['campus', 'Riverside Campus Green Cover'], ['farm', 'Green Valley Farm']]) {
    const link = page.getByRole('link', { name: new RegExp(name) }).first()
    await link.waitFor({ timeout: 10000 })
    const m = (await link.getAttribute('href'))?.match(/\/w\/([^/]+)/)
    if (!m) throw new Error(`Could not find the "${name}" workspace`)
    ids[key] = m[1]
  }
  return ids
}

async function runActions(page, actions = []) {
  for (const a of actions) {
    if (a.click) await page.locator(a.click).first().click()
    else if (a.check) await page.locator(a.check).first().check()
    else if (a.select) await page.locator(a.select.css).selectOption(a.select.value)
    else if (a.wait) await page.waitForTimeout((a.wait * 1000) / SPEED)
    await page.waitForTimeout(700 / SPEED)
  }
}

const rl = MANUAL ? readline.createInterface({ input: process.stdin, output: process.stdout }) : null
async function dwell(page, seconds) {
  if (MANUAL) await rl.question('  [Enter for the next step] ')
  else await page.waitForTimeout((seconds * 1000) / SPEED)
}

// ------------------------------------------------------------------------------------------------ main
async function launch() {
  for (const channel of ['msedge', 'chrome']) {
    try {
      return await chromium.launch({ channel, headless: false, args: ['--start-maximized'] })
    } catch {
      /* try the next one */
    }
  }
  throw new Error('Neither Microsoft Edge nor Google Chrome could be started. Install one of them, or follow docs/DEMO.md to click through the demo by hand.')
}

async function main() {
  const accounts = demoAccounts()
  const probe = await fetch(`${BASE}/`).catch(() => null)
  if (!probe || !probe.ok) throw new Error(`The web app is not answering at ${BASE}. Start it with demo.bat first.`)

  const browser = await launch()
  const context = await browser.newContext({ viewport: null })
  const page = await context.newPage()
  const failures = []
  let current = null
  try {
    let ids = null
    for (const [i, step] of steps.entries()) {
      const who = step.who ?? 'owner'
      if (who !== current) {
        if (current) await signOut(page)
        await signIn(page, accounts[who])
        current = who
        ids ??= await workspaceIds(page)
      }
      const base = step.workspace ? `${BASE}/w/${ids[step.workspace]}` : BASE
      console.log(`[${i + 1}/${steps.length}] ${step.title}`)
      try {
        await page.goto(`${base}${step.path ?? ''}`)
        if (step.openAsset) {
          await page.getByRole('link', { name: step.openAsset, exact: true }).first().click()
          await page.waitForLoadState('networkidle')
        }
        await page.waitForLoadState('networkidle')
        await caption(page, { n: i + 1, total: steps.length, who, title: step.title, text: step.caption })
        await runActions(page, step.do)
        await highlight(page, step.focus)
        if (SHOTS) await page.screenshot({ path: join(SHOTS, `${String(i + 1).padStart(2, '0')}-${step.id}.png`) })
        await dwell(page, step.dwell ?? 7)
      } catch (err) {
        failures.push(`${step.id}: ${String(err.message).split('\n')[0]}`)
        console.log(`   (skipped part of this step: ${String(err.message).split('\n')[0]})`)
      }
    }
    await caption(page, { n: steps.length, total: steps.length, who: current, title: 'That is the tour', text: 'Everything you saw ran through the real API with real rules, roles and an audit trail. Nothing was saved. Close this window whenever you like.' })
    if (flag('keep-open')) await rl?.question('Press Enter to close the browser. ')
    else await page.waitForTimeout(6000)
  } finally {
    rl?.close()
    await browser.close()
  }
  if (failures.length) {
    console.log(`\nFinished with ${failures.length} step(s) that did not fully run:\n - ${failures.join('\n - ')}`)
    process.exit(1)
  }
  console.log('\nTour finished.')
}

main().catch((err) => {
  console.error(`\nTour could not run: ${err.message}`)
  process.exit(2)
})
