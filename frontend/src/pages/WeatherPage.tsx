import { useState, type FormEvent } from 'react'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { StatusChip } from '../components/StatusChip'
import { ErrorState, LoadingBlock } from '../components/states'
import { useForecast } from '../lib/queries'
import { summarize } from '../lib/weather'

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
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) return setFormError('Latitude must be between -90 and 90.')
    if (!Number.isFinite(lon) || lon < -180 || lon > 180) return setFormError('Longitude must be between -180 and 180.')
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
        <h1 className="text-2xl font-semibold tracking-tight">Weather</h1>
        {cap && <StatusChip tone={cap.available ? 'live' : 'soon'}>{cap.available ? 'Live' : 'Disabled'}</StatusChip>}
      </header>
      <p className="max-w-prose text-ink-2">
        Forecast context for irrigation and field planning. Enter a coordinate for now; field and zone locations will replace this once they exist.
      </p>

      <form onSubmit={submit} className="grid items-end gap-3 rounded-lg border border-line bg-surface p-4 sm:grid-cols-5" noValidate>
        <div>
          <label htmlFor="lat" className="mb-1 block text-sm text-ink-2">Latitude</label>
          <input id="lat" name="lat" inputMode="decimal" required placeholder="e.g. 19.20" className="w-full rounded border border-line bg-canvas px-2 py-1.5" />
        </div>
        <div>
          <label htmlFor="lon" className="mb-1 block text-sm text-ink-2">Longitude</label>
          <input id="lon" name="lon" inputMode="decimal" required placeholder="e.g. 72.97" className="w-full rounded border border-line bg-canvas px-2 py-1.5" />
        </div>
        <div>
          <label htmlFor="days" className="mb-1 block text-sm text-ink-2">Days</label>
          <select id="days" name="days" defaultValue="3" className="w-full rounded border border-line bg-canvas px-2 py-1.5">
            {[1, 3, 7, 14].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
        <button className="rounded bg-moss px-3 py-2 text-moss-ink">Get forecast</button>
        <button type="button" onClick={(e) => fillMyLocation(e.currentTarget.form)} className="rounded border border-line px-3 py-2 hover:bg-surface-2">Use my location</button>
      </form>
      {formError && <p role="alert" className="text-sm text-critical">{formError}</p>}

      {q.isFetching && <LoadingBlock label="Fetching forecast" />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && !q.isFetching && (
        <section aria-labelledby="fc" className="space-y-3">
          <h2 id="fc" className="text-lg font-semibold">Next 24 hours</h2>
          {q.data.source === 'mock' && <p role="status" className="rounded border border-at-risk p-2 text-sm text-at-risk">Synthetic development data, not real weather.</p>}
          {summary ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Stat label="Temperature now" value={summary.temperatureC === null ? 'n/a' : `${summary.temperatureC.toFixed(1)} °C`} />
              <Stat label="Rain, next 24 h" value={summary.next24hPrecipMm === null ? 'n/a' : `${summary.next24hPrecipMm} mm`} />
              <Stat label="Max rain probability" value={summary.maxPrecipProbabilityPct === null ? 'n/a' : `${summary.maxPrecipProbabilityPct}%`} />
              <Stat label="Soil moisture, top 1 cm" value={summary.soilMoisture0to1 === null ? 'n/a' : `${summary.soilMoisture0to1.toFixed(2)} m³/m³`} />
            </div>
          ) : (
            <p className="text-sm text-ink-2">The forecast does not cover the current hour.</p>
          )}
          <p className="text-xs text-ink-3">{q.data.attribution} · timezone {q.data.timezone} · fetched {new Date(q.data.fetched_at).toLocaleString()}</p>
        </section>
      )}
    </div>
  )
}
