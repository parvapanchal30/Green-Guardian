import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { en, type Catalog, type Key } from './catalog.en'
import { hi } from './catalog.hi'

/**
 * Internationalisation (ADR-058): English and Hindi.
 *
 * - Catalogs are flat objects of dotted keys. English is the source; `hi` is typed `Catalog`, so a missing Hindi key is a
 *   compile error, and a test checks that placeholders match.
 * - `t(key, { name })` fills `{name}`. Plurals use `key_one` / `key_other` (the browser's Intl.PluralRules picks the form):
 *   `t('x', { count: 3 })` looks up `x_one` or `x_other`.
 * - A missing key falls back to English, then to the key itself, so a gap shows up as readable English, never as a blank.
 * - Dates, numbers and relative times use the browser's Intl for the chosen locale.
 * - Text composed by the SERVER (explanations, KPI bases, error messages) is not translated here yet: it arrives in English.
 * - Without a provider (unit tests of single components) everything renders in English.
 */
export type Locale = 'en' | 'hi'
export const LOCALES: { code: Locale; name: string }[] = [
  { code: 'en', name: 'English' },
  { code: 'hi', name: 'हिन्दी' },
]
export type Params = Record<string, string | number>

const CATALOGS: Record<Locale, Catalog> = { en, hi }
const STORAGE_KEY = 'gg.locale'

// Keys that may be given to t(): every key, with the plural suffix removed.
type PluralBase<K> = K extends `${infer B}_one` | `${infer B}_other` ? B : K
export type TKey = PluralBase<Key>

export function translate(locale: Locale, key: string, params?: Params): string {
  const catalog = CATALOGS[locale] as Record<string, string>
  const fallback = en as Record<string, string>
  let entry: string | undefined
  if (params && typeof params.count === 'number') {
    const rule = new Intl.PluralRules(locale).select(params.count)
    entry = catalog[`${key}_${rule}`] ?? catalog[`${key}_other`] ?? fallback[`${key}_${rule}`] ?? fallback[`${key}_other`]
  }
  entry ??= catalog[key] ?? fallback[key] ?? key
  return params ? entry.replace(/\{(\w+)\}/g, (whole, name: string) => (name in params ? String(params[name]) : whole)) : entry
}

export function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved === 'en' || saved === 'hi') return saved
  } catch {
    /* storage can be blocked: fall through */
  }
  return typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('hi') ? 'hi' : 'en'
}

export interface Formatters {
  date(iso: string | null | undefined): string
  dateTime(iso: string | null | undefined): string
  number(n: number, options?: Intl.NumberFormatOptions): string
  /** "3 days ago" / "in 2 days" / "just now", in the chosen language. */
  relative(iso: string | null | undefined, now?: Date): string
}

function formatters(locale: Locale): Formatters {
  const parse = (iso: string | null | undefined) => {
    if (!iso) return null
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? null : d
  }
  return {
    date: (iso) => parse(iso)?.toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' }) ?? '—',
    dateTime: (iso) =>
      parse(iso)?.toLocaleString(locale, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) ?? '—',
    number: (n, options) => n.toLocaleString(locale, options),
    relative: (iso, now = new Date()) => {
      if (!iso) return translate(locale, 'time.never')
      const d = parse(iso)
      if (!d) return '—'
      const diff = d.getTime() - now.getTime()
      const abs = Math.abs(diff)
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
      if (abs < 60_000) return translate(locale, 'time.justNow')
      if (abs < 3_600_000) return rtf.format(Math.round(diff / 60_000), 'minute')
      if (abs < 86_400_000) return rtf.format(Math.round(diff / 3_600_000), 'hour')
      return rtf.format(Math.round(diff / 86_400_000), 'day')
    },
  }
}

export interface I18n {
  locale: Locale
  setLocale: (l: Locale) => void
  t: (key: TKey, params?: Params) => string
  /** Label of an enumerated value (stage, role, health band...): catalog entry `<group>.<value>`, else the server's text. */
  te: (group: string, value: string, fallback?: string) => string
  fmt: Formatters
}

const humanise = (s: string) => s.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())

function build(locale: Locale, setLocale: (l: Locale) => void): I18n {
  const known = CATALOGS[locale] as Record<string, string>
  const english = en as Record<string, string>
  return {
    locale,
    setLocale,
    t: (key, params) => translate(locale, key, params),
    te: (group, value, fallback) => {
      const key = `${group}.${value}`
      return known[key] !== undefined || english[key] !== undefined ? translate(locale, key) : (fallback ?? humanise(value))
    },
    fmt: formatters(locale),
  }
}

const DEFAULT: I18n = build('en', () => undefined)
const Context = createContext<I18n>(DEFAULT)

export function I18nProvider({ children, initial }: { children: ReactNode; initial?: Locale }) {
  const [locale, setLocaleState] = useState<Locale>(initial ?? detectLocale())
  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* the choice still applies for this visit */
    }
  }, [])
  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])
  const value = useMemo(() => build(locale, setLocale), [locale, setLocale])
  return <Context.Provider value={value}>{children}</Context.Provider>
}

export const useI18n = (): I18n => useContext(Context)
export const useT = () => useContext(Context).t
