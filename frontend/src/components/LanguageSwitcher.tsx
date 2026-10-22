import { LOCALES, useI18n, type Locale } from '../i18n'

/** Choose the interface language. Each language is listed in its own script so people can find theirs. */
export function LanguageSwitcher({ className = '' }: { className?: string }) {
  const { locale, setLocale, t } = useI18n()
  return (
    <select
      aria-label={t('lang.label')}
      value={locale}
      onChange={(e) => setLocale(e.target.value as Locale)}
      className={`rounded border border-line bg-canvas px-2 py-1 text-sm ${className}`}
    >
      {LOCALES.map((l) => (
        <option key={l.code} value={l.code} lang={l.code}>{l.name}</option>
      ))}
    </select>
  )
}
