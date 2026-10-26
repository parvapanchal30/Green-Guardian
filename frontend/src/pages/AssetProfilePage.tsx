import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import type { Evidence, Observation, TimelineEvent } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { ActionPanel } from '../components/ActionPanel'
import { HealthChart } from '../components/asset/HealthChart'
import { RecordSheet, type RecordTab } from '../components/asset/RecordSheet'
import { Field, HealthChip, SeverityChip, StateChip, btn, btnPrimary, input } from '../components/domain'
import { EvidenceGallery, EvidenceImage } from '../components/EvidenceGallery'
import { HarvestPanel } from '../components/HarvestPanel'
import { Icon } from '../components/icons'
import { LifecyclePanel } from '../components/LifecyclePanel'
import { RecommendationCard } from '../components/RecommendationCard'
import { SchedulePanel } from '../components/SchedulePanel'
import { ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { Card, SectionHeading, Segmented, Tag } from '../components/ui'
import { useI18n } from '../i18n'
import { useActions } from '../lib/actions'
import { atLeast } from '../lib/format'
import { useAsset, useCreateIssue, useEvidence, useIssues, useObservations, useRecommendations, useTasks, useTimeline } from '../lib/slice'
import { GrowthPanel } from './GrowthPage'

const CATEGORIES = ['disease', 'pest', 'nutrient', 'water_stress', 'irrigation_failure', 'physical_damage', 'growth_anomaly', 'harvest_readiness', 'maintenance', 'other']

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
      <h2 className="text-lg font-semibold">{t('issueForm.title')}</h2>
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

/** One figure in the facts strip. */
function Fact({ label, value, note, tone }: { label: string; value: ReactNode; note?: ReactNode; tone?: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 border-b border-line-soft px-4 py-3 odd:border-r sm:border-b-0 sm:odd:border-r-0 sm:not-last:border-r">
      <span className="text-[12.5px] text-ink-2">{label}</span>
      <span className={`font-display text-[22px] leading-tight font-bold ${tone ?? ''}`}>{value}</span>
      {note && <span className="text-xs text-ink-2">{note}</span>}
    </div>
  )
}

type TimelineFilter = 'all' | 'observation' | 'work' | 'issues' | 'stage'
const FILTER_OF: Record<TimelineEvent['type'], TimelineFilter> = { observation: 'observation', action: 'work', harvest: 'work', issue: 'issues', task: 'issues', lifecycle: 'stage' }

function scoreOf(observations: Observation[], ev: Evidence): number | null {
  const o = ev.observation_id ? observations.find((x) => x.id === ev.observation_id) : undefined
  return o?.health_score ?? null
}

/**
 * The plant page (ADR-072): who it is (latest photo, tag, health, stage), how it has been (recorded scores with
 * photos on the same timeline), what happened, and what is open. Everything is recorded through one Record sheet.
 */
export function AssetProfilePage() {
  const { assetId = '' } = useParams()
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te, fmt, locale } = useI18n()
  const { hash } = useLocation()
  const navigate = useNavigate()
  const asset = useAsset(ws, assetId)
  const timeline = useTimeline(ws, assetId)
  const observations = useObservations(ws, assetId)
  const issues = useIssues(ws, { asset_id: assetId, limit: 50 })
  const tasks = useTasks(ws, { asset_id: assetId, is_open: true, limit: 50 })
  const recs = useRecommendations(ws, { status: 'open', asset_id: assetId })
  const evidence = useEvidence(ws, { asset_id: assetId, limit: 50 })
  const actions = useActions(ws, assetId)
  const [showIssue, setShowIssue] = useState(false)
  const [sheet, setSheet] = useState<RecordTab | null>(null)
  const [filter, setFilter] = useState<TimelineFilter>('all')
  const canObserve = atLeast(workspace.role, 'worker')
  const canDecide = atLeast(workspace.role, 'manager')

  // "Record" from the phone bar or the plant picker arrives as #record: open the sheet once, then drop the hash.
  useEffect(() => {
    if (hash !== '#record' || !canObserve) return
    // oxlint-disable-next-line react/set-state-in-effect -- reacting to navigation, which is an external event
    setSheet('observation')
    navigate({ hash: '' }, { replace: true })
  }, [hash, canObserve, navigate])

  if (asset.isLoading) return <LoadingBlock label={t('asset.loading')} />
  if (asset.error || !asset.data) return <ErrorState error={asset.error ?? new Error(t('asset.notFound'))} onRetry={() => asset.refetch()} />
  const a = asset.data
  const obs = observations.data?.items ?? []
  const latestObs = obs[0]
  const scored = obs.filter((o) => o.health_score != null).sort((x, y) => x.observed_at.localeCompare(y.observed_at))
  const firstScore = scored[0]
  const lastScore = scored[scored.length - 1]
  const change = scored.length > 1 ? Math.round((lastScore.health_score as number) - (firstScore.health_score as number)) : null
  const photos = evidence.data?.items ?? []
  const latestPhoto = photos[0]
  const photoObs = new Set(photos.map((p) => p.observation_id).filter(Boolean))
  const openIssues = (issues.data?.items ?? []).filter((i) => i.is_open)
  const openTasks = [...(tasks.data?.items ?? [])].sort((x, y) => (x.due_at ?? '9999').localeCompare(y.due_at ?? '9999'))
  const workDays = (actions.data?.history ?? []).filter((x) => x.effective && !x.withdrawn).map((x) => x.performed_at)
  const openRecs = recs.data?.items ?? []
  const issueOptions = openIssues.map((i) => ({ id: i.id, label: `${i.key} · ${i.title}` }))
  const events = (timeline.data ?? []).filter((e) => filter === 'all' || FILTER_OF[e.type] === filter)
  const photoLabel = (ev: Evidence) => {
    const s = scoreOf(obs, ev)
    return s == null ? fmt.date(ev.created_at) : t('asset2.photoScore', { date: fmt.date(ev.created_at), score: Math.round(s) })
  }
  const healthTone = a.state.health_band === 'critical' ? 'text-critical' : a.state.health_band === 'at_risk' ? 'text-at-risk' : ''

  return (
    <div className="flex flex-col gap-5">
      <nav aria-label={t('asset.breadcrumb')} className="text-sm text-ink-2"><Link to={`/w/${ws}/assets`} className="hover:underline">{t('assets.title')}</Link> / {a.label}</nav>

      <Card className="flex flex-col overflow-hidden sm:flex-row">
        <div className="relative h-56 shrink-0 bg-surface-2 sm:h-auto sm:min-h-60 sm:w-80">
          {latestPhoto ? (
            <>
              <EvidenceImage ws={ws} ev={latestPhoto} className="h-full w-full object-cover" />
              <span className="absolute bottom-2 left-2 rounded-[3px] border border-line bg-surface px-2 text-xs">{photoLabel(latestPhoto)}</span>
            </>
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center text-sm text-ink-2">
              <Icon name="photo" size={30} className="text-ink-3" />
              <span>{t('asset2.noPhoto')}</span>
              {canObserve && <button type="button" className={btn} onClick={() => setSheet('photo')}>{t('asset2.firstPhoto')}</button>}
            </div>
          )}
        </div>
        <div className="flex flex-1 flex-col gap-2 px-5 py-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            {a.tag_code && <Tag>{a.tag_code}</Tag>}
            <HealthChip band={a.state.health_band} score={a.state.health_score} />
            <StatusChip tone={a.is_active ? 'neutral' : 'critical'}>{t('asset.stage', { stage: te('stage', a.current_stage) })}</StatusChip>
            {openIssues.map((i) => <Link key={i.id} to={`/w/${ws}/issues/${i.id}`}><Tag tone="critical">{i.key}</Tag></Link>)}
          </div>
          <h1 className="text-[34px] leading-tight font-bold">{a.label}</h1>
          <p className="text-sm text-ink-2">{[a.species_name, a.location_name, te('kind', a.kind)].filter(Boolean).join(' · ') || t('asset.noSpecies')}</p>
          {a.estimated_count != null && <p className="text-sm text-ink-2">{t('asset.population', { count: fmt.number(a.estimated_count) })}</p>}
          {a.notes && <p className="max-w-prose text-sm">{a.notes}</p>}
          <div className="mt-auto flex flex-wrap gap-2 pt-2">
            {canObserve && <button type="button" className={btnPrimary} onClick={() => setSheet('observation')}><Icon name="record" size={17} />{t('navx.record')}</button>}
            {canObserve && <button type="button" className={btn} onClick={() => setSheet('photo')}><Icon name="photo" size={17} />{t('asset2.addPhoto')}</button>}
            <Link to={`/w/${ws}/monitor/map`} className={btn}><Icon name="map" size={17} />{t('asset2.showOnMap')}</Link>
            {canObserve && !showIssue && <button type="button" className={btn} onClick={() => setShowIssue(true)}>{canDecide ? t('issueForm.open') : t('issueForm.report')}</button>}
          </div>
        </div>
      </Card>

      <Card className="grid grid-cols-2 sm:grid-cols-5">
        <Fact label={t('asset2.latestHealth')} value={a.state.health_score == null ? '—' : Math.round(a.state.health_score)} tone={healthTone} note={lastScore ? fmt.date(lastScore.observed_at) : t('asset.tile.unknown')} />
        <Fact label={t('asset2.change')} value={change == null ? '—' : `${change > 0 ? '+' : change < 0 ? '−' : ''}${Math.abs(change)}`} note={change == null ? t('asset2.changeNone') : t('asset2.changeSince', { date: fmt.date(firstScore.observed_at), score: Math.round(firstScore.health_score as number) })} />
        <Fact label={t('asset2.lastLooked')} value={a.state.last_observed_at ? fmt.relative(a.state.last_observed_at) : t('asset.tile.never')} />
        <Fact label={t('asset2.photos')} value={photos.length} note={latestPhoto ? t('asset2.photosLatest', { date: fmt.date(latestPhoto.created_at) }) : undefined} />
        <Fact label={t('asset.tile.openTasks')} value={a.state.open_task_count} note={openTasks[0]?.due_at ? t('asset2.nextDue', { date: fmt.date(openTasks[0].due_at) }) : undefined} />
      </Card>

      {openRecs.length > 0 && (
        <section aria-labelledby="sugg">
          <SectionHeading id="sugg" title={t('asset.suggested')} />
          <ul className="flex flex-col gap-2">{openRecs.map((r) => <RecommendationCard key={r.id} rec={r} ws={ws} canDecide={canDecide} />)}</ul>
        </section>
      )}
      {showIssue && <CreateIssueForm ws={ws} assetId={a.id} latestObservationId={latestObs?.id} onDone={() => setShowIssue(false)} />}

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-5">
          <section aria-labelledby="chart">
            <Card className="flex flex-col gap-3 px-4 py-4 sm:px-5">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="chart" className="text-[19px] font-semibold">{t('asset2.chartTitle')}</h2>
                <span className="font-mono text-[10.5px] tracking-[0.06em] text-ink-2 uppercase">{t('asset2.chartNote')}</span>
              </div>
              <HealthChart observations={obs} workDays={workDays} />
              <div className="border-t border-line-soft pt-3">
                <h3 id="photos" className="mb-2 font-sans text-sm font-semibold">{t('asset.photos')}</h3>
                <EvidenceGallery ws={ws} assetId={a.id} canUpload={false} isManager={canDecide} labelFor={photoLabel} columns="grid-cols-2 sm:grid-cols-4" />
              </div>
            </Card>
          </section>

          <section aria-labelledby="hist">
            <SectionHeading id="hist" title={t('asset2.timeline')}>
              <Segmented
                label={t('asset2.timelineFilter')}
                value={filter}
                onChange={setFilter}
                options={[
                  { value: 'all', label: t('asset2.filter.all') },
                  { value: 'observation', label: t('asset2.filter.observation') },
                  { value: 'work', label: t('asset2.filter.work') },
                  { value: 'issues', label: t('asset2.filter.issues') },
                  { value: 'stage', label: t('asset2.filter.stage') },
                ]}
              />
            </SectionHeading>
            {timeline.isLoading && <LoadingBlock label={t('asset.loadingHistory')} />}
            {timeline.data && events.length === 0 && <p className="text-sm text-ink-2">{t('asset.noHistory')}</p>}
            {events.length > 0 && (
              <Card className="px-4 py-3 sm:px-5">
                <ol className="flex flex-col">
                  {events.map((e, i) => (
                    <li key={`${e.type}-${e.ref_id}-${i}`} className="grid grid-cols-[5.5rem_1rem_minmax(0,1fr)] gap-x-2.5 text-sm">
                      <span className="pt-0.5 font-mono text-xs text-ink-2">{fmt.date(e.at)}</span>
                      <span className="flex flex-col items-center" aria-hidden="true">
                        <span className={`mt-1.5 h-2.5 w-2.5 rounded-full border-2 bg-surface ${e.type === 'issue' ? 'border-critical' : 'border-moss'}`} />
                        {i < events.length - 1 && <span className="w-0.5 flex-1 bg-line" />}
                      </span>
                      <div className="pb-4">
                        <p className="text-xs text-ink-2">{te('timelineType', e.type)}</p>
                        <p className="font-semibold">{e.type === 'issue' ? <Link className="hover:underline" to={`/w/${ws}/issues/${e.ref_id}`}>{e.title}</Link> : e.title}</p>
                        {e.detail && <p className="text-ink-2">{e.detail}</p>}
                        {e.type === 'observation' && photoObs.has(e.ref_id) && (
                          <p className="mt-0.5 flex items-center gap-1 text-xs text-ink-2"><Icon name="photo" size={13} />{t('asset2.withPhoto')}</p>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </Card>
            )}
          </section>
        </div>

        <aside className="flex min-w-0 flex-col gap-4" aria-label={t('asset2.sidebar')}>
          <Card className="flex flex-col gap-2 px-4 py-3">
            <h2 className="text-[17px] font-semibold">{t('asset.issues')}</h2>
            {openIssues.length === 0 ? <p className="text-sm text-ink-2">{t('asset2.noOpenIssue')}</p> : (
              <ul className="flex flex-col gap-2">
                {openIssues.map((i) => (
                  <li key={i.id} className="flex flex-col gap-1 text-sm">
                    <span className="flex flex-wrap items-center gap-2"><Tag tone="critical">{i.key}</Tag><SeverityChip severity={i.severity} /><StateChip state={i.state} open={i.is_open} /></span>
                    <Link to={`/w/${ws}/issues/${i.id}`} className="font-semibold hover:underline">{i.title}</Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="flex flex-col gap-2 px-4 py-3">
            <h2 className="text-[17px] font-semibold">{t('asset.tasks')}</h2>
            {openTasks.length === 0 ? <p className="text-sm text-ink-2">{t('asset.noTasks')}</p> : (
              <ul className="flex flex-col gap-1.5 text-sm">
                {openTasks.map((task) => (
                  <li key={task.id} className="flex items-baseline gap-2.5">
                    <span className={`w-16 shrink-0 font-mono text-xs ${task.overdue ? 'text-critical' : 'text-ink-2'}`}>{task.due_at ? new Date(task.due_at).toLocaleDateString(locale, { day: 'numeric', month: 'short' }) : t('home.noDate')}</span>
                    <span className="min-w-0 flex-1">{task.issue_id ? <Link to={`/w/${ws}/issues/${task.issue_id}`} className="hover:underline">{task.title}</Link> : task.title}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="px-4 py-3"><SchedulePanel ws={ws} asset={a} role={workspace.role} compact /></Card>
          <Card className="px-4 py-3"><GrowthPanel ws={ws} assetId={a.id} /></Card>
          <Card className="px-4 py-3"><ActionPanel ws={ws} asset={a} role={workspace.role} show="history" /></Card>
          <Card className="px-4 py-3"><LifecyclePanel ws={ws} asset={a} role={workspace.role} show="history" /></Card>
          {workspace.mode === 'agricultural_production' && <Card className="px-4 py-3"><HarvestPanel ws={ws} asset={a} role={workspace.role} /></Card>}
          <Card className="flex items-center gap-3 px-4 py-3">
            <Icon name="place" size={20} className="text-moss" />
            <span className="min-w-0 flex-1">
              <span className="block font-semibold">{a.location_name ?? t('asset2.noPlace')}</span>
              {a.latitude != null && a.longitude != null && <span className="font-mono text-xs text-ink-2">{a.latitude.toFixed(4)}, {a.longitude.toFixed(4)}</span>}
            </span>
            <Link to={`/w/${ws}/monitor/map`} className="text-sm text-moss underline">{t('asset2.openMap')}</Link>
          </Card>
        </aside>
      </div>

      {sheet && <RecordSheet ws={ws} asset={a} role={workspace.role} tab={sheet} onTab={setSheet} onClose={() => setSheet(null)} issueOptions={issueOptions} />}
    </div>
  )
}
