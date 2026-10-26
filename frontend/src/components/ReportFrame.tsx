import type { ReactNode } from 'react'
import { MethodBadge, PageHeader, btn } from './domain'
import { useI18n } from '../i18n'
import { downloadCsv, toCsv } from '../lib/csv'
import { PERIODS, type usePeriod } from '../lib/reports'


/** One figure of a report: its label, value and an optional explanation. Also the row of the CSV download. */
export interface Figure {
  section: string
  label: string
  value: string | number | null
  note?: string
}

/**
 * The frame both reports share: title, period picker, Print and CSV download. `figures` is the report flattened for
 * the CSV (null while loading).
 */
export function ReportFrame({
  title, subtitle, slug, period, figures, children,
}: {
  title: string
  subtitle: string
  slug: string
  period: ReturnType<typeof usePeriod>
  figures: Figure[] | null
  children: ReactNode
}) {
  const { t, fmt } = useI18n()
  const { months, setMonths, since, until } = period

  function exportCsv() {
    if (!figures) return
    const rows = figures.map((f) => [f.section, f.label, f.value, f.note ?? ''])
    downloadCsv(`${slug}-${since.slice(0, 10)}-to-${until.slice(0, 10)}.csv`, toCsv(['section', 'figure', 'value', 'note'], rows))
  }

  return (
    <div className="space-y-6">
      <PageHeader title={title} subtitle={subtitle}>
        <MethodBadge method="statistical" />
        <button type="button" className={`${btn} print:hidden`} onClick={() => window.print()}>{t('rep.print')}</button>
        <button type="button" className={`${btn} print:hidden`} disabled={!figures} onClick={exportCsv}>{t('hv.export')}</button>
      </PageHeader>
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label={t('hv.period')} className="inline-flex overflow-hidden rounded border border-line text-sm print:hidden">
          {PERIODS.map((m) => (
            <button key={m} type="button" aria-pressed={months === m} onClick={() => setMonths(m)} className={`px-3 py-1.5 ${months === m ? 'bg-surface-2 font-medium' : 'hover:bg-surface-2'}`}>
              {t('hv.months', { count: m })}
            </button>
          ))}
        </div>
        <span className="text-sm text-ink-2">{t('rep.range', { from: fmt.date(since), to: fmt.date(until) })}</span>
      </div>
      {children}
      <p className="text-xs text-ink-3">{t('rep.note')}</p>
    </div>
  )
}

/** A labelled number in a card. */
export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3 break-inside-avoid">
      <p className="text-xs text-ink-3">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      {note && <p className="mt-1 text-xs text-ink-3">{note}</p>}
    </div>
  )
}

/** A small "name: count" list, or a dash when empty. */
export function Counts({ items, label }: { items: [string, number][]; label: string }) {
  const { fmt } = useI18n()
  if (items.length === 0) return <p className="text-sm text-ink-3">—</p>
  return (
    <ul aria-label={label} className="space-y-0.5 text-sm">
      {items.map(([name, n]) => <li key={name} className="flex justify-between gap-4"><span>{name}</span><span className="font-medium">{fmt.number(n)}</span></li>)}
    </ul>
  )
}
