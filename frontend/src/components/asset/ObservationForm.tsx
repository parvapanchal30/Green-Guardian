import { useState, type FormEvent } from 'react'
import { ProblemError } from '../../api/client'
import type { ObservationCreated } from '../../api/types'
import { useI18n } from '../../i18n'
import { checkImageFile } from '../../lib/evidence'
import { useCreateObservation, useUploadEvidence } from '../../lib/slice'
import { Field, btnPrimary, input } from '../domain'
import { errorMessage } from '../states'

/** Record what you see: a health score, symptoms, notes, measurements and an optional photo (Record sheet, ADR-072). */
export function ObservationForm({ ws, assetId, onCreated }: { ws: string; assetId: string; onCreated: (r: ObservationCreated) => void }) {
  // Suggestions made by the rules arrive through the (refreshed) open-suggestions list, not from this response.
  const { t } = useI18n()
  const create = useCreateObservation(ws)
  const upload = useUploadEvidence(ws)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    const f = new FormData(form)
    const text = (k: string) => String(f.get(k) ?? '').trim()
    const body: Record<string, unknown> = { asset_id: assetId }
    if (text('health_score') !== '') body.health_score = Number(text('health_score'))
    const symptoms = text('symptoms').split(',').map((s) => s.trim()).filter(Boolean)
    if (symptoms.length) body.symptoms = symptoms
    if (text('notes')) body.notes = text('notes')
    // Optional measurements (Growth): stored in the observation's data, checked again by the server.
    const measures: Record<string, number> = {}
    for (const [key, max] of [['height_cm', 10_000], ['girth_cm', 3_000], ['canopy_m', 100]] as const) {
      if (text(key) === '') continue
      const n = Number(text(key))
      if (!Number.isFinite(n) || n <= 0 || n > max) {
        setError(t('obs.badMeasure'))
        return
      }
      measures[key] = n
    }
    if (Object.keys(measures).length) {
      body.data = measures
      if (body.health_score === undefined) body.kind = 'growth'
    }
    const file = (form.elements.namedItem('photo') as HTMLInputElement | null)?.files?.[0] ?? null
    if (!body.health_score && body.health_score !== 0 && !symptoms.length && !body.notes && !body.data) {
      setError(t('obs.needSomething'))
      return
    }
    const problem = file ? checkImageFile(file, t) : null
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setNotice(null)
    create.mutate(body, {
      onSuccess: (r) => {
        form.reset()
        onCreated(r)
        // Observations are immutable, so a failed photo cannot undo the saved record: say exactly what happened.
        if (file) {
          upload.mutate(
            { assetId, file, caption: text('photo_caption'), observationId: r.observation.id },
            { onError: (err) => setNotice(t('obs.photoFailed', { error: errorMessage(err) })) },
          )
        }
      },
    })
  }

  const serverError = create.error instanceof ProblemError ? create.error.message : create.error ? errorMessage(create.error) : null
  return (
    <form onSubmit={submit} className="space-y-3" aria-label={t('obs.formLabel')}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="health_score" label={t('obs.health')} hint={t('obs.healthHint')}>
          <input id="health_score" name="health_score" type="number" min={0} max={100} step="any" className={input} />
        </Field>
        <Field id="symptoms" label={t('obs.symptoms')}>
          <input id="symptoms" name="symptoms" className={input} placeholder="leaf_yellowing, leaf_drop" />
        </Field>
      </div>
      <Field id="notes" label={t('obs.notes')}>
        <textarea id="notes" name="notes" rows={2} maxLength={5000} className={input} />
      </Field>
      <fieldset className="grid gap-3 rounded border border-line p-2 sm:grid-cols-3">
        <legend className="px-1 text-xs text-ink-3">{t('obs.measurements')}</legend>
        <Field id="height_cm" label={t('obs.height')}><input id="height_cm" name="height_cm" type="number" min={0} step="any" className={input} /></Field>
        <Field id="girth_cm" label={t('obs.girth')} hint={t('obs.girthHint')}><input id="girth_cm" name="girth_cm" type="number" min={0} step="any" className={input} /></Field>
        <Field id="canopy_m" label={t('obs.canopy')}><input id="canopy_m" name="canopy_m" type="number" min={0} step="any" className={input} /></Field>
      </fieldset>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="photo" label={t('obs.photo')} hint={t('obs.photoHint')}>
          <input id="photo" name="photo" type="file" accept="image/jpeg,image/png,image/webp" className={input} />
        </Field>
        <Field id="photo_caption" label={t('obs.photoCaption')}><input id="photo_caption" name="photo_caption" maxLength={500} className={input} /></Field>
      </div>
      {(error || serverError) && <p role="alert" className="text-sm text-critical">{error ?? serverError}</p>}
      {notice && <p role="alert" className="text-sm text-at-risk">{notice}</p>}
      <button className={btnPrimary} disabled={create.isPending || upload.isPending}>{create.isPending ? t('obs.saving') : upload.isPending ? t('obs.uploading') : t('obs.save')}</button>
    </form>
  )
}
