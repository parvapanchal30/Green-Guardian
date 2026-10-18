import { useRef, useState, type FormEvent } from 'react'
import { ProblemError } from '../../api/client'
import type { DatasetDetailRecord, ImportReport } from '../../api/types'
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

function Report({ r }: { r: ImportReport }) {
  return (
    <div className="space-y-2 text-sm" aria-label="Import report">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={r.ok ? 'live' : 'critical'}>{r.ok ? 'No errors' : `${r.error_count} error${r.error_count === 1 ? '' : 's'}`}</StatusChip>
        <span>{r.rows_total} rows</span>
        <span>{r.to_create} to create</span>
        <span>{r.unchanged} already registered and unchanged</span>
      </div>
      <p className="text-ink-2">{r.note} Nothing is written until you import, and a file with any error imports nothing.</p>
      {r.errors.length > 0 && (
        <table className="w-full text-left text-xs" aria-label="Import errors">
          <thead><tr className="text-ink-3"><th className="p-1">Row</th><th className="p-1">Sample</th><th className="p-1">Column</th><th className="p-1">Problem</th></tr></thead>
          <tbody>
            {r.errors.slice(0, SHOWN_ERRORS).map((e, i) => (
              <tr key={i} className="border-t border-line align-top">
                <td className="p-1">{e.row ?? 'file'}</td><td className="p-1">{e.external_id ?? ''}</td><td className="p-1">{e.column ?? ''}</td><td className="p-1">{e.message}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {(r.errors_truncated || r.errors.length > SHOWN_ERRORS) && <p className="text-xs text-ink-3">Showing the first {Math.min(SHOWN_ERRORS, r.errors.length)} of {r.error_count} errors.</p>}
      {r.warnings.length > 0 && (
        <ul aria-label="Import warnings" className="list-disc space-y-1 pl-5 text-ink-2">
          {r.warnings.map((w) => <li key={w.code}>{w.message} ({w.count} row{w.count === 1 ? '' : 's'}{w.rows.length ? `, e.g. ${w.rows.slice(0, 5).join(', ')}` : ''})</li>)}
        </ul>
      )}
    </div>
  )
}

function SingleForm({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
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
    <form onSubmit={submit} aria-label="Register one sample" className="grid gap-3 sm:grid-cols-2">
      <Field id="one-id" label="Sample identifier"><input id="one-id" className={input} value={f.external_id} onChange={(e) => setF({ ...f, external_id: e.target.value })} required /></Field>
      <Field id="one-group" label="Group (plant, plot or farm)"><input id="one-group" className={input} value={f.group_key} onChange={(e) => setF({ ...f, group_key: e.target.value })} /></Field>
      <Field id="one-label" label="Label (starts unreviewed)"><input id="one-label" className={input} value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} /></Field>
      <Field id="one-source" label="Source (where it came from)"><input id="one-source" className={input} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} required={d.kind === 'real'} /></Field>
      <div className="sm:col-span-2">
        <button className={btn} disabled={reg.isPending}>{reg.isPending ? 'Saving…' : 'Register sample'}</button>
        {reg.isSuccess && <span role="status" className="ml-2 text-sm text-ink-2">Registered {reg.data.registered} sample. Its label is unreviewed.</span>}
        {reg.error != null && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(reg.error)}</p>}
      </div>
    </form>
  )
}

export function ImportPanel({ ws, d }: { ws: string; d: DatasetDetailRecord }) {
  const imp = useImportSamples(ws, d.id)
  const fileRef = useRef<HTMLInputElement>(null)
  const [text, setText] = useState<string | null>(null)
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)
  const [report, setReport] = useState<ImportReport | null>(null)
  const [previewed, setPreviewed] = useState<string | null>(null)

  if (d.kind === 'real' && d.status !== 'approved') {
    return <p className="rounded-lg border border-line bg-surface p-3 text-sm text-ink-2">Samples of a real dataset can only be registered once it is approved. Nothing may be downloaded or imported before.</p>
  }

  const pick = async (file: File | undefined) => {
    setReport(null)
    setPreviewed(null)
    setText(null)
    setFileError(null)
    if (!file) return
    setFileName(file.name)
    if (file.size > MAX_BYTES) return setFileError('This file is larger than 2 MB. Split it into smaller files.')
    if (!/\.csv$/i.test(file.name) && file.type !== 'text/csv') return setFileError('Choose a .csv file.')
    try {
      setText(await readText(file))
    } catch {
      setFileError('The file could not be read.')
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
      <h3 className="font-medium">Add samples</h3>
      <p className="text-sm text-ink-2">
        Registering records metadata only (identifier, group, label, fingerprints, source); the images themselves are not stored here. <strong>Every imported label starts unreviewed</strong> and
        counts as validated only after a recorded review. A column that tries to carry review status is refused.
      </p>
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-sm" htmlFor="csv-file">CSV file</label>
          <input id="csv-file" ref={fileRef} type="file" accept=".csv,text/csv" onChange={(e) => void pick(e.target.files?.[0])} />
          <button type="button" className="text-xs underline" onClick={downloadTemplate}>Download a template</button>
        </div>
        <p className="text-xs text-ink-3">Columns: external_id (required), group_key, label, content_sha256, phash, file_status, width, height, source{d.kind === 'real' ? ' (required for real datasets)' : ''}. Up to 5,000 rows and 2 MB.</p>
        {fileError && <p role="alert" className="text-sm text-critical">{fileError}</p>}
        {text != null && fileName && <p className="text-xs text-ink-3">{fileName}: {text.split('\n').filter((l) => l.trim()).length - 1} data rows read in the browser. The server checks the file again.</p>}
        <div className="flex flex-wrap gap-2">
          <button type="button" className={btn} disabled={text == null || imp.isPending} onClick={() => run(false)}>{imp.isPending ? 'Checking…' : 'Preview (writes nothing)'}</button>
          <button type="button" className={btnPrimary} disabled={!canCommit || imp.isPending} onClick={() => run(true)}>{report && canCommit ? `Import ${report.to_create} sample${report.to_create === 1 ? '' : 's'}` : 'Import'}</button>
        </div>
        {report?.status === 'imported' && <p role="status" className="text-sm text-ink-2">Imported {report.to_create} samples as unreviewed.</p>}
        {report?.status === 'already_imported' && <p role="status" className="text-sm text-ink-2">Nothing to import: every row is already registered with the same values.</p>}
        {imp.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(imp.error)}</p>}
        {report && <Report r={report} />}
      </div>
      <details>
        <summary className="cursor-pointer text-sm">Register a single sample</summary>
        <div className="mt-2"><SingleForm ws={ws} d={d} /></div>
      </details>
    </div>
  )
}
