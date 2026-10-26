import { useEffect, useState, type FormEvent } from 'react'
import { ProblemError } from '../api/client'
import type { Evidence } from '../api/types'
import { useAuth } from '../lib/auth'
import { ACCEPTED_TYPES, checkImageFile } from '../lib/evidence'
import { useI18n } from '../i18n'
import { useDeleteEvidence, useEvidence, useEvidenceBlob, useUploadEvidence } from '../lib/slice'
import { Field, btn, btnPrimary, input } from './domain'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from './states'

function useBlobUrl(blob: Blob | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!blob) return
    const u = URL.createObjectURL(blob)
    // A blob URL is an external resource: it must be created and revoked with the effect (a memoised URL would be
    // revoked by StrictMode's mount/unmount/mount cycle and leave a broken image).
    // oxlint-disable-next-line react/set-state-in-effect
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [blob])
  return url
}

export function EvidenceImage({ ws, ev, className }: { ws: string; ev: Evidence; className?: string }) {
  const { t } = useI18n()
  const q = useEvidenceBlob(ws, ev)
  const url = useBlobUrl(q.data)
  if (q.error) return <button type="button" onClick={() => q.refetch()} className={`${className ?? ''} flex items-center justify-center text-xs text-critical`}>{t('evidence.loadFailed')}</button>
  if (!url) return <div className={`${className ?? ''} animate-pulse bg-surface-2`} aria-label={t('evidence.loadingImage')} />
  return <img src={url} alt={ev.caption ?? ev.original_filename ?? t('evidence.photoAlt')} className={className} />
}

function Viewer({ ws, ev, canDelete, onClose }: { ws: string; ev: Evidence; canDelete: boolean; onClose: () => void }) {
  const { t, fmt } = useI18n()
  const del = useDeleteEvidence(ws)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div role="dialog" aria-modal="true" aria-label={t('evidence.dialog')} className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="max-h-full w-full max-w-3xl overflow-auto rounded-lg bg-surface p-3" onClick={(e) => e.stopPropagation()}>
        <EvidenceImage ws={ws} ev={ev} className="mx-auto max-h-[70vh] w-auto max-w-full rounded" />
        <div className="mt-3 flex flex-wrap items-start justify-between gap-2 text-sm">
          <div>
            {ev.caption && <p className="font-medium">{ev.caption}</p>}
            <p className="text-xs text-ink-3">{fmt.dateTime(ev.created_at)} · {ev.width}×{ev.height} · {(ev.size_bytes / 1024).toFixed(0)} KB{ev.original_filename ? ` · ${ev.original_filename}` : ''}</p>
          </div>
          <div className="flex gap-2">
            {canDelete && (
              <button type="button" className={btn} disabled={del.isPending} onClick={() => del.mutate(ev.id, { onSuccess: onClose })}>
                {del.isPending ? t('evidence.removing') : t('evidence.remove')}
              </button>
            )}
            <button type="button" className={btn} onClick={onClose}>{t('evidence.close')}</button>
          </div>
        </div>
        {del.error && <p role="alert" className="mt-2 text-sm text-critical">{errorMessage(del.error)}</p>}
      </div>
    </div>
  )
}

export function EvidenceUploader({
  ws, assetId, issueId, issueOptions, observationId, onUploaded,
}: {
  ws: string; assetId: string; issueId?: string; observationId?: string
  /** Offer a "link to issue" choice (used on the asset page). */
  issueOptions?: { id: string; label: string }[]
  onUploaded?: () => void
}) {
  const { t } = useI18n()
  const upload = useUploadEvidence(ws)
  const [error, setError] = useState<string | null>(null)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const file = (form.elements.namedItem('file') as HTMLInputElement | null)?.files?.[0]
    if (!file) return setError(t('evidence.chooseFirst'))
    const problem = checkImageFile(file, t)
    if (problem) return setError(problem)
    setError(null)
    upload.mutate(
      { assetId, file, caption: String(f.get('caption') ?? ''), observationId, issueId: issueId ?? (String(f.get('issue') ?? '') || undefined) },
      { onSuccess: () => { form.reset(); onUploaded?.() } },
    )
  }

  const serverError = upload.error instanceof ProblemError ? upload.error.message : upload.error ? errorMessage(upload.error) : null
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-3" aria-label={t('evidence.uploadForm')}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="evidence-file" label={t('evidence.photo')} hint={t('evidence.photoHint')}>
          <input id="evidence-file" name="file" type="file" accept={ACCEPTED_TYPES.join(',')} className={input} onChange={() => { setError(null); upload.reset() }} />
        </Field>
        <Field id="evidence-caption" label={t('evidence.caption')}>
          <input id="evidence-caption" name="caption" maxLength={500} className={input} />
        </Field>
        {issueOptions && issueOptions.length > 0 && !issueId && (
          <Field id="evidence-issue" label={t('evidence.attachIssue')}>
            <select id="evidence-issue" name="issue" className={input} defaultValue="">
              <option value="">{t('evidence.noIssue')}</option>
              {issueOptions.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </select>
          </Field>
        )}
      </div>
      {(error || serverError) && <p role="alert" className="text-sm text-critical">{error ?? serverError}</p>}
      <button className={btnPrimary} disabled={upload.isPending}>{upload.isPending ? t('evidence.uploading') : t('evidence.uploadForm')}</button>
    </form>
  )
}

/** Photos for an asset (optionally narrowed to one issue). Read-only for viewers; workers upload; the uploader or a manager removes. */
export function EvidenceGallery({
  ws, assetId, issueId, canUpload, isManager, issueOptions, labelFor, columns = 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4',
}: {
  ws: string; assetId?: string; issueId?: string; canUpload: boolean; isManager: boolean
  issueOptions?: { id: string; label: string }[]
  /** The line under each photo; defaults to its caption, else when it was taken. */
  labelFor?: (ev: Evidence) => string
  columns?: string
}) {
  const { t, fmt } = useI18n()
  const { user } = useAuth()
  const q = useEvidence(ws, issueId ? { issue_id: issueId, limit: 50 } : { asset_id: assetId, limit: 50 })
  const [open, setOpen] = useState<Evidence | null>(null)
  const items = q.data?.items ?? []

  return (
    <div className="space-y-3">
      {canUpload && assetId && <EvidenceUploader ws={ws} assetId={assetId} issueId={issueId} issueOptions={issueOptions} />}
      {q.isLoading && <LoadingBlock label={t('evidence.loading')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && items.length === 0 && (
        <EmptyState title={t('evidence.none')}>{canUpload ? t('evidence.noneCanUpload') : t('evidence.noneReadOnly')}</EmptyState>
      )}
      {items.length > 0 && (
        <ul className={`grid gap-3 ${columns}`}>
          {items.map((ev) => (
            <li key={ev.id}>
              <button type="button" onClick={() => setOpen(ev)} className="block w-full overflow-hidden rounded-lg border border-line bg-surface text-left hover:border-ink-3" aria-label={ev.caption ? t('evidence.openWithCaption', { caption: ev.caption }) : t('evidence.open')}>
                <EvidenceImage ws={ws} ev={ev} className="aspect-[4/3] w-full object-cover" />
                <span className="block truncate p-1.5 text-xs text-ink-2">{labelFor ? labelFor(ev) : ev.caption ?? fmt.dateTime(ev.created_at)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {open && <Viewer ws={ws} ev={open} canDelete={isManager || open.uploaded_by === user?.id} onClose={() => setOpen(null)} />}
    </div>
  )
}
