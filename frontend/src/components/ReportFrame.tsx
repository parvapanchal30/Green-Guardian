import type { ReactNode } from 'react'
import { MethodBadge, PageHeader, btn } from './domain'
import { Icon } from './icons'
import { Segmented, StatTile } from './ui'
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
  title, subtitle, slug, period, figures, summary, children,
}: {
  title: string
  /** The figures put into words by a fixed template (ADR-077), shown before them. */
  summary?: string | null
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
    <div className="flex flex-col gap-5">
      <PageHeader eyebrow={t('eyebrow.reports')} title={title} subtitle={subtitle}>
        <MethodBadge method="statistical" />
        <button type="button" className={`${btn} print:hidden`} onClick={() => window.print()}><Icon name="print" size={16} />{t('rep.print')}</button>
        <button type="button" className={`${btn} print:hidden`} disabled={!figures} onClick={exportCsv}><Icon name="download" size={16} />{t('hv.export')}</button>
      </PageHeader>
      <div className="flex flex-wrap items-center gap-3">
        <span className="print:hidden">
          <Segmented label={t('hv.period')} value={String(months)} onChange={(v) => setMonths(Number(v) as typeof months)} options={PERIODS.map((m) => ({ value: String(m), label: t('hv.months', { count: m }) }))} />
        </span>
        <span className="font-mono text-xs text-ink-2">{t('rep.range', { from: fmt.date(since), to: fmt.date(until) })}</span>
      </div>
      {summary && (
        <section aria-label={t('rep.summary')} className="rounded-lg border border-line bg-surface px-4 py-3.5">
          <p className="font-mono text-[10.5px] tracking-wide text-ink-2 uppercase">{t('rep.summaryNote')}</p>
          <p className="mt-1 font-display text-xl leading-snug font-semibold">{summary}</p>
        </section>
      )}
      {children}
      <p className="text-[13px] text-ink-2">{t('rep.note')}</p>
    </div>
  )
}

/** A labelled number in a card. */
export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="break-inside-avoid">
      <StatTile label={label} value={value} note={note} />
    </div>
  )
}

/** A small "name: count" list, or a dash when empty. */
export function Counts({ items, label }: { items: [string, number][]; label: string }) {
  const { fmt } = useI18n()
  if (items.length === 0) return <p className="text-sm text-ink-3">—</p>
  return (
    <ul aria-label={label} className="flex flex-col text-sm">
      {items.map(([name, n]) => <li key={name} className="flex justify-between gap-4 border-b border-line-soft py-1 last:border-0"><span>{name}</span><span className="font-mono font-medium">{fmt.number(n)}</span></li>)}
    </ul>
  )
}
