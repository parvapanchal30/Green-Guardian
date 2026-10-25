import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ObservationCreated } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { EvidenceGallery } from '../components/EvidenceGallery'
import { ActionPanel } from '../components/ActionPanel'
import { HarvestPanel } from '../components/HarvestPanel'
import { SchedulePanel } from '../components/SchedulePanel'
import { LifecyclePanel } from '../components/LifecyclePanel'
import { RecommendationCard } from '../components/RecommendationCard'
import { Field, HealthChip, PageHeader, SeverityChip, StateChip, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { ProblemError } from '../api/client'
import { checkImageFile } from '../lib/evidence'
import { useI18n } from '../i18n'
import { atLeast } from '../lib/format'
import { useAsset, useCreateIssue, useCreateObservation, useIssues, useObservations, useRecommendations, useTasks, useTimeline, useUploadEvidence } from '../lib/slice'

const CATEGORIES = ['disease', 'pest', 'nutrient', 'water_stress', 'irrigation_failure', 'physical_damage', 'growth_anomaly', 'harvest_readiness', 'maintenance', 'other']

function ObservationForm({ ws, assetId, onCreated }: { ws: string; assetId: string; onCreated: (r: ObservationCreated) => void }) {
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
    const file = (form.elements.namedItem('photo') as HTMLInputElement | null)?.files?.[0] ?? null
    if (!body.health_score && body.health_score !== 0 && !symptoms.length && !body.notes) {
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
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-4" aria-label={t('obs.formLabel')}>
      <h2 className="font-semibold">{t('obs.title')}</h2>
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

function CreateIssueForm({ ws, assetId, latestObservationId, onDone }: { ws: string; assetId: string; latestObservationId?: string; onDone: () => void }) {
  const { t, te } = useI18n()
  const create = useCreateIssue(ws)
  const [linkEvidence, setLinkEvidence] = useState(true)
  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const body: Record<string, unknown> = {
      title: String(f.get('title')).trim(), category: f.get('category'), severity: f.get('severity'),
      description: String(f.get('description') ?? '').trim() || undefined, asset_id: assetId,
    }
    if (linkEvidence && latestObservationId) body.observation_id = latestObservationId
    create.mutate(body, { onSuccess: onDone })
  }
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-4" aria-label={t('issueForm.label')}>
      <h2 className="font-semibold">{t('issueForm.title')}</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-3"><Field id="title" label={t('issueForm.field.title')}><input id="title" name="title" required maxLength={300} className={input} placeholder={t('issueForm.field.titlePlaceholder')} /></Field></div>
        <Field id="category" label={t('issueForm.field.category')}>
          <select id="category" name="category" className={input} defaultValue="disease">{CATEGORIES.map((c) => <option key={c} value={c}>{te('issueCategory', c)}</option>)}</select>
        </Field>
        <Field id="severity" label={t('issueForm.field.severity')}>
          <select id="severity" name="severity" className={input} defaultValue="medium">{['low', 'medium', 'high', 'critical'].map((s) => <option key={s} value={s}>{te('severity', s)}</option>)}</select>
        </Field>
      </div>
      <Field id="description" label={t('issueForm.field.description')}><textarea id="description" name="description" rows={2} className={input} /></Field>
      {latestObservationId && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={linkEvidence} onChange={(e) => setLinkEvidence(e.target.checked)} /> {t('issueForm.attachLatest')}</label>
      )}
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2"><button className={btnPrimary} disabled={create.isPending}>{t('issueForm.open')}</button><button type="button" className={btn} onClick={onDone}>{t('issueForm.cancel')}</button></div>
    </form>
  )
}

export function AssetProfilePage() {
  const { assetId = '' } = useParams()
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt } = useI18n()
  const asset = useAsset(ws, assetId)
  const timeline = useTimeline(ws, assetId)
  const observations = useObservations(ws, assetId)
  const issues = useIssues(ws, { asset_id: assetId, limit: 50 })
  const tasks = useTasks(ws, { asset_id: assetId, limit: 50 })
  const recs = useRecommendations(ws, { status: 'open', asset_id: assetId })
  const [showIssue, setShowIssue] = useState(false)
  const canObserve = atLeast(workspace.role, 'worker')
  const canDecide = atLeast(workspace.role, 'manager')

  if (asset.isLoading) return <LoadingBlock label={t('asset.loading')} />
  if (asset.error || !asset.data) return <ErrorState error={asset.error ?? new Error(t('asset.notFound'))} onRetry={() => asset.refetch()} />
  const a = asset.data
  const latestObs = observations.data?.items[0]
  const openRecs = recs.data?.items ?? []

  return (
    <div className="space-y-6">
      <nav aria-label={t('asset.breadcrumb')} className="text-sm text-ink-3"><Link to={`/w/${ws}/assets`} className="hover:underline">{t('assets.title')}</Link> / {a.label}</nav>
      <PageHeader
        title={a.label}
        subtitle={<>{[a.species_name, a.location_name, a.tag_code].filter(Boolean).join(' · ') || t('asset.noSpecies')}</>}
      >
        <HealthChip band={a.state.health_band} score={a.state.health_score} />
        <StatusChip tone="neutral">{t('asset.stage', { stage: te('stage', a.current_stage) })}</StatusChip>
        {canDecide && !showIssue && <button type="button" className={btn} onClick={() => setShowIssue(true)}>{t('issueForm.open')}</button>}
        {!canDecide && atLeast(workspace.role, 'worker') && !showIssue && <button type="button" className={btn} onClick={() => setShowIssue(true)}>{t('issueForm.report')}</button>}
      </PageHeader>

      <section aria-label={t('asset.currentState')} className="grid gap-3 sm:grid-cols-4">
        {[
          [t('asset.tile.health'), a.state.health_score == null ? t('asset.tile.unknown') : `${Math.round(a.state.health_score)} / 100`],
          [t('asset.tile.lastObserved'), a.state.last_observed_at ? fmt.relative(a.state.last_observed_at) : t('asset.tile.never')],
          [t('asset.tile.openIssues'), String(a.state.open_issue_count)],
          [t('asset.tile.openTasks'), String(a.state.open_task_count)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-line bg-surface p-3"><p className="text-sm text-ink-2">{k}</p><p className="mt-1 text-lg font-semibold">{v}</p></div>
        ))}
      </section>
      {a.estimated_count && <p className="text-sm text-ink-2">{t('asset.population', { count: fmt.number(a.estimated_count) })}</p>}
      {a.notes && <p className="max-w-prose text-sm text-ink-2">{a.notes}</p>}

      {openRecs.length > 0 && (
        <section aria-labelledby="sugg">
          <h2 id="sugg" className="mb-2 font-semibold">{t('asset.suggested')}</h2>
          <ul className="space-y-2">{openRecs.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
        </section>
      )}

      {showIssue && <CreateIssueForm ws={ws} assetId={a.id} latestObservationId={latestObs?.id} onDone={() => setShowIssue(false)} />}
      {canObserve && <ObservationForm ws={ws} assetId={a.id} onCreated={() => undefined} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="iss">
          <h2 id="iss" className="mb-2 font-semibold">{t('asset.issues')}</h2>
          {issues.data?.items.length ? (
            <ul className="space-y-2">{issues.data.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
                <Link className="font-medium text-moss hover:underline" to={`/w/${ws}/issues/${i.id}`}>{i.key}</Link><span>{i.title}</span>
                <SeverityChip severity={i.severity} /><StateChip state={i.state} open={i.is_open} />
              </li>))}</ul>
          ) : <p className="text-sm text-ink-3">{t('asset.noIssues')}</p>}
        </section>
        <section aria-labelledby="tsk">
          <h2 id="tsk" className="mb-2 font-semibold">{t('asset.tasks')}</h2>
          {tasks.data?.items.length ? (
            <ul className="space-y-2">{tasks.data.items.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
                <Link className="font-medium text-moss hover:underline" to={`/w/${ws}/tasks`}>{t.key}</Link><span>{t.title}</span><TaskStatusChip status={t.status} overdue={t.overdue} />
              </li>))}</ul>
          ) : <p className="text-sm text-ink-3">{t('asset.noTasks')}</p>}
        </section>
      </div>

      <LifecyclePanel ws={ws} asset={a} role={workspace.role} />
      <ActionPanel ws={ws} asset={a} role={workspace.role} />
      <SchedulePanel ws={ws} asset={a} role={workspace.role} />
      {workspace.mode === 'agricultural_production' && <HarvestPanel ws={ws} asset={a} role={workspace.role} />}

      <section aria-labelledby="photos">
        <h2 id="photos" className="mb-2 font-semibold">{t('asset.photos')}</h2>
        <EvidenceGallery
          ws={ws}
          assetId={a.id}
          canUpload={canObserve}
          isManager={canDecide}
          issueOptions={issues.data?.items.filter((i) => i.is_open).map((i) => ({ id: i.id, label: `${i.key} · ${i.title}` }))}
        />
      </section>

      <section aria-labelledby="hist">
        <h2 id="hist" className="mb-2 font-semibold">{t('asset.history')}</h2>
        {timeline.isLoading && <LoadingBlock label={t('asset.loadingHistory')} />}
        {timeline.data?.length === 0 && <p className="text-sm text-ink-3">{t('asset.noHistory')}</p>}
        <ol className="space-y-2 border-l border-line pl-4">
          {timeline.data?.map((e, i) => (
            <li key={`${e.type}-${e.ref_id}-${i}`} className="text-sm">
              <p className="text-xs text-ink-3">{fmt.dateTime(e.at)} · {te('timelineType', e.type)}</p>
              <p className="font-medium">{e.type === 'issue' ? <Link className="text-moss hover:underline" to={`/w/${ws}/issues/${e.ref_id}`}>{e.title}</Link> : e.title}</p>
              {e.detail && <p className="text-ink-2">{e.detail}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
