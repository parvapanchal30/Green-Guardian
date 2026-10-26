import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import type { Forecast, Task } from '../api/types'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader, btn, btnPrimary } from '../components/domain'
import { Icon, type IconName } from '../components/icons'
import { EmptyState, ErrorState, LoadingBlock, errorMessage } from '../components/states'
import { Card, SectionHeading, Segmented, Tag } from '../components/ui'
import { PinMap } from '../components/weather/PinMap'
import { WeatherChart, type WeatherMetric } from '../components/weather/WeatherChart'
import { useI18n, type TKey } from '../i18n'
import { atLeast } from '../lib/format'
import { useForecast, usePlaceSearch, useSavedPlaces, useWeatherPlaceChanges, type FoundPlace } from '../lib/queries'
import { useLocations, useTasks } from '../lib/slice'
import { dailyForecast, dayKind, rainAdvice, weekGlance, type DayForecast, type DayKind } from '../lib/weather'

const KIND_ICON: Record<DayKind, IconName> = { dry: 'dry', showers: 'showers', rain: 'rain', unknown: 'weather' }
const METRICS: WeatherMetric[] = ['temp', 'rain', 'water', 'soil']

interface Place { key: string; name: string; note: string; lat: number; lon: number; savedId?: string }

function useDayName() {
  const { locale } = useI18n()
  return (date: string, style: 'short' | 'long' = 'short') => new Date(`${date}T12:00:00`).toLocaleDateString(locale, { weekday: style })
}
function useShortDate() {
  const { locale } = useI18n()
  return (date: string) => new Date(`${date}T12:00:00`).toLocaleDateString(locale, { day: 'numeric', month: 'short' })
}
const deg = (v: number | null) => (v === null ? '—' : `${Math.round(v)}°`)

/** Weather (ADR-075): "My places" (fields, zones and saved places, seven days) and "Any place" (search or pin). */
export function WeatherPage() {
  const { t } = useI18n()
  const { capabilities } = useWorkspaceCtx()
  const [tab, setTab] = useState<'mine' | 'any'>('mine')
  const cap = capabilities?.find((c) => c.key === 'weather_context')
  const tabs = [
    { id: 'mine' as const, label: t('weather.tab.mine') },
    { id: 'any' as const, label: t('weather.tab.any') },
  ]
  return (
    <div className="flex flex-col gap-4">
      <PageHeader eyebrow={t('eyebrow.monitor')} title={t('weather.title')} subtitle={t('weather.subtitle')}>
        {cap && <Tag tone={cap.available ? 'moss' : 'neutral'}>{cap.available ? t('weather.forecastTag') : t('weather.disabled')}</Tag>}
      </PageHeader>
      <div role="tablist" aria-label={t('weather.title')} className="flex gap-6 border-b border-line">
        {tabs.map((x) => (
          <button
            key={x.id}
            type="button"
            role="tab"
            id={`wtab-${x.id}`}
            aria-selected={tab === x.id}
            aria-controls="wpanel"
            onClick={() => setTab(x.id)}
            className={`-mb-px border-b-2 py-2.5 text-[15px] ${tab === x.id ? 'border-moss font-semibold text-ink' : 'border-transparent text-ink-2 hover:text-ink'}`}
          >
            {x.label}
          </button>
        ))}
      </div>
      <div id="wpanel" role="tabpanel" aria-labelledby={`wtab-${tab}`}>
        {tab === 'mine' ? <MyPlaces onFindPlace={() => setTab('any')} /> : <AnyPlace onSaved={() => setTab('mine')} />}
      </div>
    </div>
  )
}

// ------------------------------------------------------------------------------------------------ My places

function MyPlaces({ onFindPlace }: { onFindPlace: () => void }) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, te } = useI18n()
  const locations = useLocations(ws)
  const saved = useSavedPlaces(ws)
  const changes = useWeatherPlaceChanges(ws)
  const isManager = atLeast(workspace.role, 'manager')
  const places: Place[] = useMemo(
    () => [
      ...(locations.data?.items ?? [])
        .filter((l) => l.latitude != null && l.longitude != null)
        .map((l) => ({ key: `l-${l.id}`, name: l.name, note: te('locationKind', l.kind), lat: l.latitude as number, lon: l.longitude as number })),
      ...(saved.data ?? []).map((p) => ({ key: `s-${p.id}`, name: p.name, note: t('weather.savedPlace'), lat: p.latitude, lon: p.longitude, savedId: p.id })),
    ],
    [locations.data, saved.data, t, te],
  )
  const [chosen, setChosen] = useState<string | null>(null)
  const place = places.find((p) => p.key === chosen) ?? places[0]

  if (locations.isLoading || saved.isLoading) return <LoadingBlock label={t('weather.fetching')} />
  if (locations.error) return <ErrorState error={locations.error} onRetry={() => locations.refetch()} />
  if (!place) {
    return (
      <EmptyState icon="weather" title={t('weather.noPlaces')} action={<button type="button" className={btnPrimary} onClick={onFindPlace}>{t('weather.findPlace')}</button>}>
        {t('weather.noPlacesBody')}
      </EmptyState>
    )
  }
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        {places.length <= 5 ? (
          <Segmented label={t('weather.place')} value={place.key} onChange={setChosen} options={places.map((p) => ({ value: p.key, label: p.name }))} />
        ) : (
          <>
            <label htmlFor="wplace" className="sr-only">{t('weather.place')}</label>
            <select id="wplace" value={place.key} onChange={(e) => setChosen(e.target.value)} className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm">
              {places.map((p) => <option key={p.key} value={p.key}>{p.name} · {p.note}</option>)}
            </select>
          </>
        )}
        <span className="text-[13px] text-ink-2">{place.note}</span>
        {place.savedId && isManager && (
          <button type="button" className={`${btn} ml-auto px-2.5 py-1 text-xs`} disabled={changes.remove.isPending} onClick={() => changes.remove.mutate(place.savedId!, { onSuccess: () => setChosen(null) })}>
            <Icon name="remove" size={14} />
            {t('weather.removePlace', { name: place.name })}
          </button>
        )}
      </div>
      {changes.remove.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(changes.remove.error)}</p>}
      <PlaceWeek key={place.key} place={place} />
    </div>
  )
}

function PlaceWeek({ place }: { place: Place }) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const dayName = useDayName()
  const shortDate = useShortDate()
  const q = useForecast(ws, { lat: place.lat, lon: place.lon, days: 7 })
  const tasks = useTasks(ws, { is_open: true, limit: 100 })
  const [sel, setSel] = useState(0)
  const [metric, setMetric] = useState<WeatherMetric>('temp')

  if (q.isLoading) return <LoadingBlock label={t('weather.fetching')} />
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return null
  const days = dailyForecast(q.data).slice(0, 7)
  const day = days[Math.min(sel, days.length - 1)]
  if (!day) return <p className="text-sm text-ink-2">{t('weather.noCurrentHour')}</p>
  const dueOn = (date: string) => (tasks.data?.items ?? []).filter((x) => x.due_at && localDate(x.due_at) === date)
  const advice = rainAdvice(q.data, new Date(q.dataUpdatedAt), workspace.settings)
  const week = weekGlance(days)

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[13px] text-ink-2">{t('weather.forPlace', { name: place.name, when: fmt.relative(q.data.fetched_at) })}</p>
      {q.data.source === 'mock' && <p role="status" className="rounded-md border border-at-risk/50 bg-at-risk-soft px-3 py-2 text-sm text-at-risk">{t('weather.mock')}</p>}
      <section aria-label={t('weather.next7')} className="relative overflow-x-auto pb-1">
        <div className="flex gap-2 md:grid md:grid-cols-7">
          {days.map((d, i) => {
            const k = dayKind(d)
            const due = dueOn(d.date).length
            return (
              <button
                key={d.date}
                type="button"
                aria-pressed={i === sel}
                onClick={() => setSel(i)}
                className={`relative flex w-[104px] shrink-0 flex-col gap-1.5 rounded-lg border bg-surface p-2.5 text-left md:w-auto ${i === sel ? 'border-moss ring-1 ring-moss' : 'border-line hover:border-ink-3'}`}
              >
                <span className="flex items-baseline justify-between gap-1">
                  <b className="text-sm">{i === 0 ? t('weather.today') : dayName(d.date)}</b>
                  <span className="font-mono text-[11px] text-ink-2">{shortDate(d.date)}</span>
                </span>
                <span className="flex items-center gap-2">
                  <Icon name={KIND_ICON[k]} size={22} className={k === 'dry' ? 'text-at-risk' : k === 'unknown' ? 'text-ink-3' : 'text-info'} />
                  <span className="text-sm"><b>{deg(d.hi)}</b> <span className="text-ink-2">{deg(d.lo)}</span></span>
                </span>
                <span className="sr-only">{t(`weather.kind.${k}` as TKey)}</span>
                <span className="h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
                  <span className="block h-full bg-info" style={{ width: `${d.rainChance ?? 0}%` }} />
                </span>
                <span className="font-mono text-[11px] text-ink-2">{t('weather.rainShort', { pct: Math.round(d.rainChance ?? 0), mm: fmt.number(d.rainMm ?? 0, { maximumFractionDigits: 1 }) })}</span>
                {due > 0 && <span className="self-start"><Tag tone="moss">{t('weather.tasksDue', { count: due })}</Tag></span>}
              </button>
            )
          })}
        </div>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="p-4">
          <section aria-labelledby="wday">
            <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 id="wday" className="text-[19px] font-semibold">{dayName(day.date, 'long')} {shortDate(day.date)}</h2>
                <p className="text-sm text-ink-2">{t(`weather.kind.${dayKind(day)}` as TKey)} · {t('weather.daySummary', { hi: deg(day.hi), lo: deg(day.lo), mm: fmt.number(day.rainMm ?? 0, { maximumFractionDigits: 1 }), pct: Math.round(day.rainChance ?? 0) })}</p>
              </div>
              <Segmented label={t('weather.show')} value={metric} onChange={setMetric} options={METRICS.map((m) => ({ value: m, label: t(`weather.metric.${m}` as TKey) }))} />
            </div>
            <WeatherChart hours={day.hours} metric={metric} />
            <p className="mt-2 text-xs text-ink-2">{t('weather.notMeasured', { attribution: q.data.attribution })}</p>
          </section>
        </Card>

        <aside className="flex flex-col gap-3">
          <Card className="p-4">
            <section aria-labelledby="wwork">
              <SectionHeading id="wwork" title={t('weather.workDue', { day: sel === 0 ? t('weather.today').toLowerCase() : dayName(day.date, 'long') })} />
              <DueList ws={ws} tasks={dueOn(day.date)} />
            </section>
          </Card>
          <RainAdviceCard advice={advice} />
          <Card className="p-4">
            <section aria-labelledby="wweek" className="flex flex-col gap-1.5 text-sm">
              <SectionHeading id="wweek" title={t('weather.week')} />
              <span>{week.rainMm === null ? t('weather.na') : t('weather.weekRain', { mm: fmt.number(week.rainMm, { maximumFractionDigits: 1 }) })}{week.wettest && <> · {t('weather.wettest', { day: dayName(week.wettest.date, 'long') })}</>}</span>
              {week.hottest && <span>{t('weather.hottest', { day: dayName(week.hottest.date, 'long'), t: deg(week.hottest.hi) })}</span>}
              <span className="text-ink-2">{week.dry.length ? t('weather.dryDays', { days: week.dry.map((d) => dayName(d.date)).join(', ') }) : t('weather.noDryDays')}</span>
            </section>
          </Card>
        </aside>
      </div>
    </div>
  )
}

/** The browser's local date of an instant, YYYY-MM-DD. */
function localDate(iso: string) {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function DueList({ ws, tasks }: { ws: string; tasks: Task[] }) {
  const { t } = useI18n()
  if (tasks.length === 0) return <p className="text-sm text-ink-2">{t('weather.nothingDue')}</p>
  return (
    <ul className="flex flex-col gap-2 text-sm">
      {tasks.map((x) => (
        <li key={x.id} className="flex items-start gap-2">
          <Tag>{x.key}</Tag>
          <span className="min-w-0">
            {x.issue_id ? <Link className="hover:underline" to={`/w/${ws}/issues/${x.issue_id}`}>{x.title}</Link> : x.asset_id ? <Link className="hover:underline" to={`/w/${ws}/assets/${x.asset_id}`}>{x.title}</Link> : x.title}
          </span>
        </li>
      ))}
    </ul>
  )
}

function RainAdviceCard({ advice }: { advice: ReturnType<typeof rainAdvice> }) {
  const { t, fmt } = useI18n()
  return (
    <Card className="p-4">
      <section aria-labelledby="wrule" className="flex flex-col gap-1.5 text-sm">
        <SectionHeading id="wrule" title={t('weather.rainAdvice')}>
          <span className="font-mono text-[11px] text-ink-2">RULE · irrigation_defer</span>
        </SectionHeading>
        <span className={advice.meets ? 'font-semibold text-info' : ''}>
          {advice.meets === null
            ? t('weather.adviceUnknown')
            : t(advice.meets ? 'weather.adviceMeets' : 'weather.adviceBelow', { mm: fmt.number(advice.rainMm ?? 0, { maximumFractionDigits: 1 }), pct: Math.round(advice.chance ?? 0) })}
        </span>
        <span className="text-[13px] text-ink-2">{t('weather.adviceRule', { mm: advice.minMm, pct: advice.minChance })}</span>
      </section>
    </Card>
  )
}

// ------------------------------------------------------------------------------------------------ Any place

function AnyPlace({ onSaved }: { onSaved: () => void }) {
  const { ws, workspace } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const locations = useLocations(ws)
  const start = locations.data?.items.find((l) => l.latitude != null && l.longitude != null)
  const [text, setText] = useState('')
  const [q, setQ] = useState('')
  const [point, setPoint] = useState<{ lat: number; lon: number; name: string; region: string } | null>(null)
  const [located, setLocated] = useState<string | null>(null)
  const search = usePlaceSearch(ws, q)
  const changes = useWeatherPlaceChanges(ws)
  const isManager = atLeast(workspace.role, 'manager')
  const fc = useForecast(ws, point ? { lat: point.lat, lon: point.lon, days: 3 } : null)

  useEffect(() => {
    const id = window.setTimeout(() => setQ(text.trim()), 350)
    return () => window.clearTimeout(id)
  }, [text])

  const pick = (p: FoundPlace) => setPoint({ lat: p.latitude, lon: p.longitude, name: p.name, region: p.region })
  const moved = (lat: number, lon: number) => setPoint((prev) => ({ lat, lon, name: prev?.name && prev.name !== t('weather.pinned') ? t('weather.near', { name: prev.name }) : t('weather.pinned'), region: prev?.region ?? '' }))
  function mine() {
    setLocated(null)
    if (!navigator.geolocation) return setLocated(t('weather.noGeo'))
    navigator.geolocation.getCurrentPosition(
      (p) => setPoint({ lat: p.coords.latitude, lon: p.coords.longitude, name: t('weather.myLocationName'), region: '' }),
      () => setLocated(t('weather.geoDenied')),
    )
  }
  function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!point) return
    const name = String(new FormData(e.currentTarget).get('pname') ?? '').trim() || point.name
    changes.save.mutate({ name, region: point.region || null, latitude: point.lat, longitude: point.lon }, { onSuccess: onSaved })
  }
  const center = point ?? (start ? { lat: start.latitude as number, lon: start.longitude as number } : { lat: 20.5, lon: 78.9 })

  return (
    <div className="grid items-start gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
      <Card className="flex flex-col gap-3 p-4">
        <section aria-labelledby="wfind" className="flex flex-col gap-3">
          <SectionHeading id="wfind" title={t('weather.findPlace')} />
          <div className="relative">
            <label className="sr-only" htmlFor="wq">{t('weather.searchLabel')}</label>
            <Icon name="search" size={16} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-3" />
            <input id="wq" type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder={t('weather.searchLabel')} className="w-full rounded-md border border-line bg-surface py-2 pr-2.5 pl-8 text-sm" />
          </div>
          <button type="button" className={`${btn} self-start`} onClick={mine}><Icon name="locate" size={16} />{t('weather.myLocation')}</button>
          {located && <p role="alert" className="text-sm text-critical">{located}</p>}
          {search.isFetching && <p className="text-sm text-ink-2">{t('weather.searching')}</p>}
          {search.error != null && <p role="alert" className="text-sm text-critical">{errorMessage(search.error)}</p>}
          {search.data && (
            <>
              {search.data.items.length === 0 ? (
                <p className="text-sm text-ink-2">{t('weather.noResults')}</p>
              ) : (
                <ul aria-label={t('weather.results')} className="flex flex-col">
                  {search.data.items.map((p) => (
                    <li key={`${p.latitude},${p.longitude}`}>
                      <button type="button" onClick={() => pick(p)} className="flex w-full flex-col rounded-md px-2 py-1.5 text-left hover:bg-surface-2">
                        <b className="text-sm">{p.name}</b>
                        <span className="text-xs text-ink-2">{p.region}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-ink-3">{search.data.attribution}</p>
            </>
          )}
          <p className="text-xs text-ink-3">{t('weather.searchNote')}</p>
        </section>
      </Card>

      <div className="flex flex-col gap-4">
        <section aria-label={t('weather.mapLabel')} className="relative h-[380px] overflow-hidden rounded-lg border border-line">
          <PinMap lat={center.lat} lon={center.lon} zoom={point ? 11 : start ? 10 : 4} onMove={moved} />
          <p className="pointer-events-none absolute top-2 left-1/2 z-[500] -translate-x-1/2 rounded-full bg-surface/95 px-3 py-1 text-xs shadow">{t('weather.dragHint')}</p>
        </section>
        {!point ? (
          <p className="text-sm text-ink-2">{t('weather.pickFirst')}</p>
        ) : (
          <Card className="p-4">
            <section aria-labelledby="wpfc" className="flex flex-col gap-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h2 id="wpfc" className="text-[19px] font-semibold">{t('weather.next3', { name: point.name })}</h2>
                <span className="font-mono text-xs text-ink-2">{coords(point.lat, point.lon, fmt.number)}{point.region && <span className="font-sans"> · {point.region}</span>}</span>
              </div>
              {fc.isLoading && <LoadingBlock label={t('weather.fetching')} />}
              {fc.error && <ErrorState error={fc.error} onRetry={() => fc.refetch()} />}
              {fc.data && <ThreeDays fc={fc.data} />}
              {isManager ? (
                <form onSubmit={save} className="flex flex-wrap items-end gap-2 border-t border-line-soft pt-3" aria-label={t('weather.saveForm')}>
                  <div>
                    <label htmlFor="pname" className="mb-1 block text-sm font-semibold">{t('weather.placeName')}</label>
                    <input id="pname" name="pname" key={point.name} defaultValue={point.name} maxLength={120} className="rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm" />
                  </div>
                  <button className={btnPrimary} disabled={changes.save.isPending}><Icon name="add" size={16} />{t('weather.save')}</button>
                  {changes.save.error != null && <p role="alert" className="w-full text-sm text-critical">{errorMessage(changes.save.error)}</p>}
                  <p className="w-full text-xs text-ink-2">{t('weather.saveNote')}</p>
                </form>
              ) : (
                <p className="border-t border-line-soft pt-3 text-xs text-ink-2">{t('weather.saveManagers')}</p>
              )}
            </section>
          </Card>
        )}
      </div>
    </div>
  )
}

function coords(lat: number, lon: number, num: (v: number, o?: Intl.NumberFormatOptions) => string) {
  const f = (v: number) => num(Math.abs(v), { maximumFractionDigits: 4, minimumFractionDigits: 4 })
  return `${f(lat)}° ${lat >= 0 ? 'N' : 'S'}, ${f(lon)}° ${lon >= 0 ? 'E' : 'W'}`
}

function ThreeDays({ fc }: { fc: Forecast }) {
  const { t, fmt } = useI18n()
  const dayName = useDayName()
  const shortDate = useShortDate()
  const days: DayForecast[] = dailyForecast(fc).slice(0, 3)
  return (
    <>
      {fc.source === 'mock' && <p role="status" className="rounded-md border border-at-risk/50 bg-at-risk-soft px-3 py-2 text-sm text-at-risk">{t('weather.mock')}</p>}
      <ul className="grid gap-2 sm:grid-cols-3">
        {days.map((d) => (
          <li key={d.date} className="flex flex-col gap-1.5 rounded-lg border border-line-soft p-3">
            <span className="flex items-baseline justify-between"><b>{dayName(d.date)}</b><span className="font-mono text-[11px] text-ink-2">{shortDate(d.date)}</span></span>
            <span className="flex items-center gap-2">
              <Icon name={KIND_ICON[dayKind(d)]} size={22} className={dayKind(d) === 'dry' ? 'text-at-risk' : 'text-info'} />
              <span><b>{deg(d.hi)}</b> <span className="text-ink-2">{deg(d.lo)}</span></span>
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden="true"><span className="block h-full bg-info" style={{ width: `${d.rainChance ?? 0}%` }} /></span>
            <span className="font-mono text-[11px] text-ink-2">{t('weather.rainShort', { pct: Math.round(d.rainChance ?? 0), mm: fmt.number(d.rainMm ?? 0, { maximumFractionDigits: 1 }) })}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-ink-2">{t('weather.notMeasured', { attribution: fc.attribution })}</p>
    </>
  )
}
