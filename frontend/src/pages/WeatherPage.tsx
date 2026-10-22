import { useState, type FormEvent } from 'react'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { StatusChip } from '../components/StatusChip'
import { ErrorState, LoadingBlock } from '../components/states'
import { useForecast } from '../lib/queries'
import { summarize } from '../lib/weather'
import { useI18n } from '../i18n'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <p className="text-sm text-ink-2">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  )
}

export function WeatherPage() {
  const { ws, capabilities } = useWorkspaceCtx()
  const { t, fmt } = useI18n()
  const [coords, setCoords] = useState<{ lat: number; lon: number; days: number } | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const q = useForecast(ws, coords)
  const cap = capabilities?.find((c) => c.key === 'weather_context')

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    const lat = Number(f.get('lat'))
    const lon = Number(f.get('lon'))
    const days = Number(f.get('days'))
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) return setFormError(t('weather.latError'))
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) return setFormError(t('weather.lonError'))
    setFormError(null)
    setCoords({ lat, lon, days })
  }

  function fillMyLocation(form: HTMLFormElement | null) {
    navigator.geolocation?.getCurrentPosition((p) => {
      if (!form) return
      ;(form.elements.namedItem('lat') as HTMLInputElement).value = p.coords.latitude.toFixed(4)
      ;(form.elements.namedItem('lon') as HTMLInputElement).value = p.coords.longitude.toFixed(4)
    })
  }

  // Evaluated at fetch time (not render time) so the summary is stable between re-renders.
  const summary = q.data ? summarize(q.data, new Date(q.dataUpdatedAt)) : null

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{t('weather.title')}</h1>
        {cap && <StatusChip tone={cap.available ? 'live' : 'soon'}>{cap.available ? t('weather.live') : t('weather.disabled')}</StatusChip>}
      </header>
      <p className="max-w-prose text-ink-2">
        {t('weather.intro')}
      </p>

      <form onSubmit={submit} className="grid items-end gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-5" noValidate>
        <div>
          <label htmlFor="lat" className="mb-1 block text-sm text-ink-2">{t('weather.latitude')}</label>
          <input id="lat" name="lat" inputMode="decimal" required placeholder={t('weather.example', { v: '19.20' })} className="w-full rounded border border-line bg-canvas px-2 py-1.5" />
        </div>
        <div>
          <label htmlFor="lon" className="mb-1 block text-sm text-ink-2">{t('weather.longitude')}</label>
          <input id="lon" name="lon" inputMode="decimal" required placeholder={t('weather.example', { v: '72.97' })} className="w-full rounded border border-line bg-canvas px-2 py-1.5" />
        </div>
        <div>
          <label htmlFor="days" className="mb-1 block text-sm text-ink-2">{t('weather.days')}</label>
          <select id="days" name="days" defaultValue="3" className="w-full rounded border border-line bg-canvas px-2 py-1.5">
            {[1, 3, 7, 14].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <button className="rounded bg-moss px-3 py-2 text-moss-ink">{t('weather.get')}</button>
        <button type="button" onClick={(e) => fillMyLocation(e.currentTarget.form)} className="rounded border border-line px-3 py-2 hover:bg-surface-2">{t('weather.myLocation')}</button>
      </form>
      {formError && <p role="alert" className="text-sm text-critical">{formError}</p>}

      {q.isFetching && <LoadingBlock label={t('weather.fetching')} />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && !q.isFetching && (
        <section aria-labelledby="fc" className="space-y-3">
          <h2 id="fc" className="text-lg font-semibold">{t('weather.next24')}</h2>
          {q.data.source === 'mock' && <p role="status" className="rounded border border-at-risk p-2 text-sm text-at-risk">{t('weather.mock')}</p>}
          {summary ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label={t('weather.tempNow')} value={summary.temperatureC === null ? t('weather.na') : `${summary.temperatureC.toFixed(1)} °C`} />
              <Stat label={t('weather.rain24')} value={summary.next24hPrecipMm === null ? t('weather.na') : `${summary.next24hPrecipMm} mm`} />
              <Stat label={t('weather.maxProb')} value={summary.maxPrecipProbabilityPct === null ? t('weather.na') : `${summary.maxPrecipProbabilityPct}%`} />
              <Stat label={t('weather.soil')} value={summary.soilMoisture0to1 === null ? t('weather.na') : `${summary.soilMoisture0to1.toFixed(2)} m³/m³`} />
            </div>
          ) : (
            <p className="text-sm text-ink-2">{t('weather.noCurrentHour')}</p>
          )}
          <p className="text-xs text-ink-3">{t('weather.footer', { attribution: q.data.attribution, tz: q.data.timezone, when: fmt.dateTime(q.data.fetched_at) })}</p>
        </section>
      )}
    </div>
  )
}
