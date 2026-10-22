import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ROUTES, routeKey, routeSummaryKey } from '../app/routes'
import { ComingSoonPanel } from '../components/CapabilityGate'
import { DatasetStatusChip, LabelStatusChip } from '../components/datasets/shared'
import { HealthChip, Pagination, SeverityChip, TaskStatusChip } from '../components/domain'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { ErrorState } from '../components/states'
import { I18nProvider, detectLocale, translate, useI18n } from '../i18n'
import { en } from '../i18n/catalog.en'
import { hi } from '../i18n/catalog.hi'

const placeholders = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()

afterEach(() => {
  localStorage.clear()
  document.documentElement.lang = 'en'
  vi.unstubAllGlobals()
})

describe('catalogs', () => {
  it('Hindi has exactly the English keys', () => {
    expect(Object.keys(hi).sort()).toEqual(Object.keys(en).sort())
  })

  it('every translation keeps the same placeholders, so no value is lost or left as {raw}', () => {
    for (const [key, text] of Object.entries(en)) expect(placeholders((hi as Record<string, string>)[key]), key).toEqual(placeholders(text))
  })

  it('no Hindi entry is empty or simply copied from English (except brand and unit abbreviations)', () => {
    const sameOnPurpose = new Set<string>()
    for (const [key, text] of Object.entries(en)) {
      const h = (hi as Record<string, string>)[key]
      expect(h.trim().length, key).toBeGreaterThan(0)
      if (h === text) sameOnPurpose.add(key)
    }
    // Entries that are legitimately the same in both languages (symbols only). Anything else here is an untranslated copy.
    expect([...sameOnPurpose].sort()).toEqual(['issue.moveTo'])
  })

  it('plural keys come in complete pairs', () => {
    for (const key of Object.keys(en)) {
      if (key.endsWith('_one')) expect(Object.keys(en)).toContain(key.replace(/_one$/, '_other'))
    }
  })
})

describe('translate', () => {
  it('fills placeholders and picks plural forms in both languages', () => {
    expect(translate('en', 'dash.empty.allExited', { count: 1 })).toMatch(/^1 registered asset has left/)
    expect(translate('en', 'dash.empty.allExited', { count: 3 })).toMatch(/^3 registered assets have left/)
    expect(translate('hi', 'dash.empty.allExited', { count: 3 })).toMatch(/^3 दर्ज संपत्तियाँ/)
    expect(translate('hi', 'tour.stepOf', { n: 2, total: 9 })).toBe('चरण 2 / 9')
  })

  it('falls back to English, then to the key, never to a blank', () => {
    expect(translate('hi', 'no.such.key')).toBe('no.such.key')
    expect(translate('en', 'tour.stepOf', { n: 1 })).toBe('Step 1 of {total}') // a missing value stays visible
  })
})

function Probe() {
  const { locale, t, te, fmt } = useI18n()
  return (
    <div>
      <p data-testid="locale">{locale}</p>
      <p data-testid="t">{t('nav.signOut')}</p>
      <p data-testid="te">{te('stage', 'flowering')}</p>
      <p data-testid="te-unknown">{te('issueState', 'awaiting_parts')}</p>
      <p data-testid="te-server">{te('stage', 'unheard_of', 'From the server')}</p>
      <p data-testid="rel">{fmt.relative('2026-10-19T12:00:00Z', new Date('2026-10-22T12:00:00Z'))}</p>
      <p data-testid="never">{fmt.relative(null)}</p>
      <LanguageSwitcher />
    </div>
  )
}

describe('provider and switcher', () => {
  it('renders in English without a provider (unit tests of single components rely on it)', () => {
    render(<HealthChip band="at_risk" score={61} />)
    expect(screen.getByText(/At risk · 61/)).toBeInTheDocument()
  })

  it('switches language, remembers it and sets the page language for screen readers', async () => {
    render(<I18nProvider initial="en"><Probe /></I18nProvider>)
    expect(screen.getByTestId('t')).toHaveTextContent('Sign out')
    expect(screen.getByTestId('rel')).toHaveTextContent('3 days ago')
    await userEvent.selectOptions(screen.getByLabelText('Language'), 'hi')
    expect(screen.getByTestId('locale')).toHaveTextContent('hi')
    expect(screen.getByTestId('t')).toHaveTextContent('साइन आउट')
    expect(screen.getByTestId('te')).toHaveTextContent('फूल आना')
    expect(screen.getByTestId('rel')).toHaveTextContent('3 दिन पहले')
    expect(screen.getByTestId('never')).toHaveTextContent('कभी नहीं')
    expect(screen.getByLabelText('भाषा')).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('hi')
    expect(localStorage.getItem('gg.locale')).toBe('hi')
  })

  it('shows values it has no translation for as readable text (humanised, or the server text)', () => {
    render(<I18nProvider initial="hi"><Probe /></I18nProvider>)
    expect(screen.getByTestId('te-unknown')).toHaveTextContent('Awaiting parts')
    expect(screen.getByTestId('te-server')).toHaveTextContent('From the server')
  })

  it('starts from the saved choice, else from the browser language', () => {
    localStorage.setItem('gg.locale', 'hi')
    expect(detectLocale()).toBe('hi')
    localStorage.clear()
    vi.stubGlobal('navigator', { language: 'hi-IN' })
    expect(detectLocale()).toBe('hi')
    vi.stubGlobal('navigator', { language: 'en-GB' })
    expect(detectLocale()).toBe('en')
    localStorage.setItem('gg.locale', 'xx') // a tampered value is ignored
    expect(detectLocale()).toBe('en')
  })
})

describe('migrated components in Hindi', () => {
  it('chips, error state and the language switcher', () => {
    render(
      <I18nProvider initial="hi">
        <MemoryRouter>
          <HealthChip band="critical" score={22} />
          <HealthChip band={null} />
          <SeverityChip severity="high" />
          <TaskStatusChip status="in_progress" overdue />
          <ErrorState error={new Error('boom')} onRetry={() => undefined} />
        </MemoryRouter>
      </I18nProvider>,
    )
    expect(screen.getByText(/गंभीर · 22/)).toBeInTheDocument()
    expect(screen.getByText('स्वास्थ्य डेटा नहीं')).toBeInTheDocument()
    expect(screen.getByText('उच्च')).toBeInTheDocument()
    expect(screen.getByText('जारी है')).toBeInTheDocument()
    expect(screen.getByText('समय सीमा बीत चुकी')).toBeInTheDocument()
    expect(screen.getByText('इसे लोड नहीं किया जा सका')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'फिर से कोशिश करें' })).toBeInTheDocument()
  })

  it('coming-soon panel, dataset chips and pagination', () => {
    render(
      <I18nProvider initial="hi">
        <ComingSoonPanel title="x" stage="v2" technique="Machine learning" />
        <DatasetStatusChip status="under_review" />
        <LabelStatusChip status="unreviewed" />
        <Pagination total={60} limit={25} offset={25} onChange={() => undefined} />
      </I18nProvider>,
    )
    expect(screen.getByText('जल्द आ रहा है')).toBeInTheDocument()
    expect(screen.getByText('V2 · पूर्वानुमान')).toBeInTheDocument()
    expect(screen.getByText('तकनीक: Machine learning')).toBeInTheDocument() // server text is shown as sent
    expect(screen.getByText(/यह सुविधा चालू होने तक/)).toBeInTheDocument()
    expect(screen.getByText('उम्मीदवार: समीक्षा में')).toBeInTheDocument()
    expect(screen.getByText('समीक्षा नहीं हुई')).toBeInTheDocument()
    expect(screen.getByText('60 में से 26–50')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'अगला' })).toBeInTheDocument()
  })

  it('every navigation route has a translated label, and a summary when it has one', () => {
    for (const r of ROUTES) {
      expect(Object.keys(hi), r.path).toContain(routeKey(r))
      if (r.summary) expect((en as Record<string, string>)[routeSummaryKey(r)], r.path).toBe(r.summary)
    }
  })
})
