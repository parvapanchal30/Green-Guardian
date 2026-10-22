import { useRef, useState, type FormEvent } from 'react'
import { ProblemError } from '../../api/client'
import type { DatasetDetailRecord, ImportReport } from '../../api/types'
import { useI18n } from '../../i18n'
import { useImportSamples, useRegisterSample } from '../../lib/datasets'
import { Field, btn, btnPrimary, input } from '../domain'
import { errorMessage } from '../states'
import { StatusChip } from '../StatusChip'

const MAX_BYTES = 2_000_000
const SHOWN_ERRORS = 50
const TEMPLATE = 'external_id,group_key,label,content_sha256,phash,file_status,width,height,source\n'

function readText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(file)
  })
}

/** The report the server sent with a refused import (422 import_invalid), if any. */
function reportFrom(error: unknown): ImportReport | null {
  if (error instanceof ProblemError && error.body.report && typeof error.body.report === 'object') return error.body.report as ImportReport
  return null
}

// Row-level error and warning messages come from the server and are shown as written.
function Report({ r }: { r: ImportReport }) {
  const { t } = useI18n()
  return (
    <div className="space-y-2 text-sm" aria-label={t('ds.im.report')}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.ok ? 'live' : 'critical'}>{r.ok ? t('ds.im.noErrors') : t('ds.im.errors', { count: r.error_count })}</StatusChip>
        <span>{t('ds.im.rows', { n: r.rows_total })}</span>
        <span>{t('ds.im.toCreate', { n: r.to_create })}</span>
        <span>{t('ds.im.unchanged', { n: r.unchanged })}</span>
      </div>
      <p className="text-ink-2">{r.note} {t('ds.im.nothingWritten')}</p>
      {r.errors.length > 0 && (
        <table className="w-full text-left text-xs" aria-label={t('ds.im.errorsTable')}>
          <thead><tr className="text-ink-3"><th className="p-1">{t('ds.im.row')}</th><th className="p-1">{t('ds.im.sample')}</th><th className="p-1">{t('ds.im.column')}</th><th className="p-1">{t('ds.im.problem')}</th></tr></thead>
          <tbody>
            {r.errors.slice(0, SHOWN_ERRORS).map((e, i) => (
              <tr key={i} className="border-t border-line align-top">
                <td className="p-1">{e.row ?? t('ds.im.file')}</td><td className="p-1">{e.external_id ?? ''}</td><td className="p-1">{e.column ?? ''}</td><td className="p-1">{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(r.errors_truncated || r.errors.length > SHOWN_ERRORS) && <p className="text-xs text-ink-3">{t('ds.im.showingFirst', { shown: Math.min(SHOWN_ERRORS, r.errors.length), total: r.error_count })}</p>}
      {r.warnings.length > 0 && (
        <ul aria-label={t('ds.im.warnings')} className="list-disc space-y-1 pl-5 text-ink-2">
          {r.warnings.map((w) => <li key={w.code}>{w.message} ({t('ds.im.warnRows', { count: w.count })}{w.rows.length ? `, ${t('ds.q.examples', { list: w.rows.slice(0, 5).join(', ') })}` : ''})</li>)}
        </ul>
      )}
    </div>
  )
}

function SingleForm({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const { t } = useI18n()
  const reg = useRegisterSample(ws, d.id)
  const blank = { external_id: '', group_key: '', label: '', source: '' }
  const [f, setF] = useState(blank)
  const submit = (e: FormEvent) => {
    e.preventDefault()
    reg.mutate(
      { samples: [{ external_id: f.external_id.trim(), group_key: f.group_key.trim() || undefined, label: f.label.trim() || undefined, provenance: f.source.trim() ? { source: f.source.trim() } : {} }] },
      { onSuccess: () => setF(blank) },
    )
  }
  return (
    <form onSubmit={submit} aria-label={t('ds.im.singleForm')} className="grid gap-3 sm:grid-cols-2">
      <Field id="one-id" label={t('ds.im.sampleId')}><input id="one-id" className={input} value={f.external_id} onChange={(e) => setF({ ...f, external_id: e.target.value })} required /></Field>
      <Field id="one-group" label={t('ds.im.group')}><input id="one-group" className={input} value={f.group_key} onChange={(e) => setF({ ...f, group_key: e.target.value })} /></Field>
      <Field id="one-label" label={t('ds.im.label')}><input id="one-label" className={input} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
      <Field id="one-source" label={t('ds.im.source')}><input id="one-source" className={input} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} required={d.kind === 'real'} /></Field>
      <div className="sm:col-span-2">
        <button className={btn} disabled={reg.isPending}>{reg.isPending ? t('ds.saving') : t('ds.im.register')}</button>
        {reg.isSuccess && <span role="status" className="ml-2 text-sm text-ink-2">{t('ds.im.registered', { n: reg.data.registered })}</span>}
        {reg.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(reg.error)}</p>}
      </div>
    </form>
  )
}

export function ImportPanel({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const { t } = useI18n()
  const imp = useImportSamples(ws, d.id)
  const fileRef = useRef<HTMLInputElement>(null)
  const [text, setText] = useState<string | null>(null)
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [previewed, setPreviewed] = useState<string | null>(null)

  if (d.kind === 'real' && d.status !== 'approved') {
    return <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">{t('ds.im.notApproved')}</p>
  }

  const pick = async (file: File | undefined) => {
    setReport(null)
    setPreviewed(null)
    setText(null)
    setFileError(null)
    if (!file) return
    setFileName(file.name)
    if (file.size > MAX_BYTES) return setFileError(t('ds.im.tooLarge'))
    if (!/\.csv$/i.test(file.name) && file.type !== 'text/csv') return setFileError(t('ds.im.chooseCsv'))
    try {
      setText(await readText(file))
    } catch {
      setFileError(t('ds.im.unreadable'))
    }
  }
  const run = (commit: boolean) => {
    if (text == null) return
    imp.mutate(
      { csv_text: text, commit },
      {
        onSuccess: (r) => { setReport(r); setPreviewed(commit ? null : text) },
        onError: (e) => { const r = reportFrom(e); if (r) setReport(r) },
      },
    )
  }
  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'samples-template.csv'
    a.click()
    URL.revokeObjectURL(url)
  }
  const canCommit = report?.status === 'preview' && report.ok && report.to_create > 0 && previewed === text && text != null

  return (
    <div className="space-y-4 rounded-lg border border-line bg-surface p-3">
      <h3 className="font-medium">{t('ds.im.title')}</h3>
      <p className="text-sm text-ink-2">
        {t('ds.im.intro1')} <strong>{t('ds.im.introBold')}</strong> {t('ds.im.intro2')}
      </p>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm" htmlFor="csv-file">{t('ds.im.csvFile')}</label>
          <input id="csv-file" ref={fileRef} type="file" accept=".csv,text/csv" onChange={(e) => void pick(e.target.files?.[0])} />
          <button type="button" className="text-xs underline" onClick={downloadTemplate}>{t('ds.im.template')}</button>
        </div>
        <p className="text-xs text-ink-3">{t('ds.im.columns', { real: d.kind === 'real' ? t('ds.im.requiredReal') : '' })}</p>
        {fileError && <p role="alert" className="text-sm text-critical">{fileError}</p>}
        {text != null && fileName && <p className="text-xs text-ink-3">{t('ds.im.readInBrowser', { file: fileName, n: text.split('\n').filter((l) => l.trim()).length - 1 })}</p>}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btn} disabled={text == null || imp.isPending} onClick={() => run(false)}>{imp.isPending ? t('ds.im.checking') : t('ds.im.preview')}</button>
          <button type="button" className={btnPrimary} disabled={!canCommit || imp.isPending} onClick={() => run(true)}>{report && canCommit ? t('ds.im.importN', { count: report.to_create }) : t('ds.im.import')}</button>
        </div>
        {report?.status === 'imported' && <p role="status" className="text-sm text-ink-2">{t('ds.im.imported', { n: report.to_create })}</p>}
        {report?.status === 'already_imported' && <p role="status" className="text-sm text-ink-2">{t('ds.im.already')}</p>}
        {imp.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(imp.error)}</p>}
        {report && <Report r={report} />}
      </div>
      <details>
        <summary className="cursor-pointer text-sm">{t('ds.im.single')}</summary>
        <div className="mt-2"><SingleForm ws={ws} d={d} /></div>
      </details>
    </div>
  )
}
