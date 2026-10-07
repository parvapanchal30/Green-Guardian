import { useState, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { ObservationCreated } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { RecommendationCard } from '../components/RecommendationCard'
import { Field, HealthChip, PageHeader, SeverityChip, StateChip, TaskStatusChip, btn, btnPrimary, input } from '../components/domain'
import { ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { ProblemError } from '../api/client'
import { atLeast, fmtDateTime, label, relative } from '../lib/format'
import { useAsset, useCreateIssue, useCreateObservation, useIssues, useObservations, useRecommendations, useTasks, useTimeline } from '../lib/slice'

const CATEGORIES = ['disease', 'pest', 'nutrient', 'water_stress', 'irrigation_failure', 'physical_damage', 'growth_anomaly', 'harvest_readiness', 'maintenance', 'other']

function ObservationForm({ ws, assetId, onCreated }: { ws: string; assetId: string; onCreated: (r: ObservationCreated) => void }) {
  // Suggestions made by the rules arrive through the (refreshed) open-suggestions list, not from this response.
  const create = useCreateObservation(ws)
  const [error, setError] = useState<string | null>(null)

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
    if (text('photo_url')) {
      body.attachments = [{ name: text('photo_name') || 'photo', content_type: text('photo_type') || 'image/jpeg', url: text('photo_url'), caption: text('photo_caption') || undefined }]
    }
    if (!body.health_score && body.health_score !== 0 && !symptoms.length && !body.notes && !body.attachments) {
      setError('Record at least a health score, symptoms, notes or a photo reference.')
      return
    }
    setError(null)
    create.mutate(body, { onSuccess: (r) => { form.reset(); onCreated(r) } })
  }

  const serverError = create.error instanceof ProblemError ? create.error.message : create.error ? errorMessage(create.error) : null
  return (
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-4" aria-label="Record observation">
      <h2 className="font-semibold">Record an observation</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="health_score" label="Health score (0–100)" hint="Healthy ≥ 70 · At risk 40–69 · Critical < 40">
          <input id="health_score" name="health_score" type="number" min={0} max={100} step="any" className={input} />
        </Field>
        <Field id="symptoms" label="Symptoms (comma separated)">
          <input id="symptoms" name="symptoms" className={input} placeholder="leaf_yellowing, leaf_drop" />
        </Field>
      </div>
      <Field id="notes" label="Notes">
        <textarea id="notes" name="notes" rows={2} maxLength={5000} className={input} />
      </Field>
      <details className="text-sm">
        <summary className="cursor-pointer text-ink-2">Attach photo reference (optional)</summary>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          <Field id="photo_url" label="Photo URL (https)" hint="File upload arrives with the storage feature; for now only a reference is stored.">
            <input id="photo_url" name="photo_url" type="url" className={input} placeholder="https://…" />
          </Field>
          <Field id="photo_caption" label="Caption"><input id="photo_caption" name="photo_caption" className={input} /></Field>
          <input type="hidden" name="photo_name" value="photo" />
          <input type="hidden" name="photo_type" value="image/jpeg" />
        </div>
      </details>
      {(error || serverError) && <p role="alert" className="text-sm text-critical">{error ?? serverError}</p>}
      <button className={btnPrimary} disabled={create.isPending}>{create.isPending ? 'Saving…' : 'Save observation'}</button>
    </form>
  )
}

function CreateIssueForm({ ws, assetId, latestObservationId, onDone }: { ws: string; assetId: string; latestObservationId?: string; onDone: () => void }) {
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
    <form onSubmit={submit} className="space-y-3 rounded-lg border border-line bg-surface p-4" aria-label="Create issue">
      <h2 className="font-semibold">Open a botanical issue</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-3"><Field id="title" label="Title"><input id="title" name="title" required maxLength={300} className={input} placeholder="e.g. Leaf yellowing" /></Field></div>
        <Field id="category" label="Category">
          <select id="category" name="category" className={input} defaultValue="disease">{CATEGORIES.map((c) => <option key={c} value={c}>{label(c)}</option>)}</select>
        </Field>
        <Field id="severity" label="Severity">
          <select id="severity" name="severity" className={input} defaultValue="medium">{['low', 'medium', 'high', 'critical'].map((s) => <option key={s} value={s}>{label(s)}</option>)}</select>
        </Field>
      </div>
      <Field id="description" label="Description"><textarea id="description" name="description" rows={2} className={input} /></Field>
      {latestObservationId && (
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={linkEvidence} onChange={(e) => setLinkEvidence(e.target.checked)} /> Attach the latest observation as evidence</label>
      )}
      {create.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(create.error)}</p>}
      <div className="flex gap-2"><button className={btnPrimary} disabled={create.isPending}>Open issue</button><button type="button" className={btn} onClick={onDone}>Cancel</button></div>
    </form>
  )
}

export function AssetProfilePage() {
  const { assetId = '' } = useParams()
  const { ws, workspace } = useWorkspaceCtx()
  const asset = useAsset(ws, assetId)
  const timeline = useTimeline(ws, assetId)
  const observations = useObservations(ws, assetId)
  const issues = useIssues(ws, { asset_id: assetId, limit: 50 })
  const tasks = useTasks(ws, { asset_id: assetId, limit: 50 })
  const recs = useRecommendations(ws, { status: 'open', asset_id: assetId })
  const [showIssue, setShowIssue] = useState(false)
  const canObserve = atLeast(workspace.role, 'worker')
  const canDecide = atLeast(workspace.role, 'manager')

  if (asset.isLoading) return <LoadingBlock label="Loading asset" />
  if (asset.error || !asset.data) return <ErrorState error={asset.error ?? new Error('Asset not found')} onRetry={() => asset.refetch()} />
  const a = asset.data
  const latestObs = observations.data?.items[0]
  const openRecs = recs.data?.items ?? []

  return (
    <div className="space-y-6">
      <nav aria-label="Breadcrumb" className="text-sm text-ink-3"><Link to={`/w/${ws}/assets`} className="hover:underline">Assets</Link> / {a.label}</nav>
      <PageHeader
        title={a.label}
        subtitle={<>{[a.species_name, a.location_name, a.tag_code].filter(Boolean).join(' · ') || 'No species or location set'}</>}
      >
        <HealthChip band={a.state.health_band} score={a.state.health_score} />
        <StatusChip tone="neutral">Stage: {label(a.current_stage)}</StatusChip>
        {canDecide && !showIssue && <button type="button" className={btn} onClick={() => setShowIssue(true)}>Open issue</button>}
        {!canDecide && atLeast(workspace.role, 'worker') && !showIssue && <button type="button" className={btn} onClick={() => setShowIssue(true)}>Report issue</button>}
      </PageHeader>

      <section aria-label="Current state" className="grid gap-3 sm:grid-cols-4">
        {[
          ['Health', a.state.health_score == null ? 'Unknown' : `${Math.round(a.state.health_score)} / 100`],
          ['Last observed', a.state.last_observed_at ? `${relative(a.state.last_observed_at)}` : 'Never'],
          ['Open issues', String(a.state.open_issue_count)],
          ['Open tasks', String(a.state.open_task_count)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-line bg-surface p-3"><p className="text-sm text-ink-2">{k}</p><p className="mt-1 text-lg font-semibold">{v}</p></div>
        ))}
      </section>
      {a.estimated_count && <p className="text-sm text-ink-2">Tracked as a population of about {a.estimated_count.toLocaleString()} plants.</p>}
      {a.notes && <p className="max-w-prose text-sm text-ink-2">{a.notes}</p>}

      {openRecs.length > 0 && (
        <section aria-labelledby="sugg">
          <h2 id="sugg" className="mb-2 font-semibold">Suggested by rules</h2>
          <ul className="space-y-2">{openRecs.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
        </section>
      )}

      {showIssue && <CreateIssueForm ws={ws} assetId={a.id} latestObservationId={latestObs?.id} onDone={() => setShowIssue(false)} />}
      {canObserve && <ObservationForm ws={ws} assetId={a.id} onCreated={() => undefined} />}

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="iss">
          <h2 id="iss" className="mb-2 font-semibold">Issues</h2>
          {issues.data?.items.length ? (
            <ul className="space-y-2">{issues.data.items.map((i) => (
              <li key={i.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
                <Link className="font-medium text-moss hover:underline" to={`/w/${ws}/issues/${i.id}`}>{i.key}</Link><span>{i.title}</span>
                <SeverityChip severity={i.severity} /><StateChip state={i.state} open={i.is_open} />
              </li>))}</ul>
          ) : <p className="text-sm text-ink-3">No issues for this asset.</p>}
        </section>
        <section aria-labelledby="tsk">
          <h2 id="tsk" className="mb-2 font-semibold">Tasks</h2>
          {tasks.data?.items.length ? (
            <ul className="space-y-2">{tasks.data.items.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface p-2 text-sm">
                <Link className="font-medium text-moss hover:underline" to={`/w/${ws}/tasks`}>{t.key}</Link><span>{t.title}</span><TaskStatusChip status={t.status} overdue={t.overdue} />
              </li>))}</ul>
          ) : <p className="text-sm text-ink-3">No tasks for this asset.</p>}
        </section>
      </div>

      <section aria-labelledby="hist">
        <h2 id="hist" className="mb-2 font-semibold">History</h2>
        {timeline.isLoading && <LoadingBlock label="Loading history" />}
        {timeline.data?.length === 0 && <p className="text-sm text-ink-3">Nothing has been recorded yet. Record the first observation above.</p>}
        <ol className="space-y-2 border-l border-line pl-4">
          {timeline.data?.map((e, i) => (
            <li key={`${e.type}-${e.ref_id}-${i}`} className="text-sm">
              <p className="text-xs text-ink-3">{fmtDateTime(e.at)} · {label(e.type)}</p>
              <p className="font-medium">{e.type === 'issue' ? <Link className="text-moss hover:underline" to={`/w/${ws}/issues/${e.ref_id}`}>{e.title}</Link> : e.title}</p>
              {e.detail && <p className="text-ink-2">{e.detail}</p>}
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}
