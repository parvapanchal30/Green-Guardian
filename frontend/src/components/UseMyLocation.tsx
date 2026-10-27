import { useState } from 'react'
import { useI18n } from '../i18n'
import { btn } from './domain'
import { Icon } from './icons'

type Status = { kind: 'idle' } | { kind: 'busy' } | { kind: 'ok'; accuracy: number } | { kind: 'error'; message: string }

/**
 * "Use my location" (ADR-079): asks the device for its position once and hands back latitude and longitude, rounded to
 * 5 decimals (about 1 m). It says what happened: the accuracy the device reported, or why there is no position. The
 * browser asks the person for permission; nothing is sent anywhere by this button.
 */
export function UseMyLocation({ onLocated }: { onLocated: (lat: number, lon: number) => void }) {
  const { t, fmt } = useI18n()
  const [status, setStatus] = useState<Status>({ kind: 'idle' })

  function locate() {
    if (!('geolocation' in navigator)) return setStatus({ kind: 'error', message: t('geo.unsupported') })
    setStatus({ kind: 'busy' })
    navigator.geolocation.getCurrentPosition(
      (p) => {
        onLocated(Number(p.coords.latitude.toFixed(5)), Number(p.coords.longitude.toFixed(5)))
        setStatus({ kind: 'ok', accuracy: p.coords.accuracy })
      },
      (e) =>
        setStatus({
          kind: 'error',
          message: e.code === e.PERMISSION_DENIED ? t('geo.denied') : e.code === e.TIMEOUT ? t('geo.timeout') : t('geo.unavailable'),
        }),
      { enableHighAccuracy: true, timeout: 15_000, maximumAge: 60_000 },
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={btn} onClick={locate} disabled={status.kind === 'busy'}>
        <Icon name="locate" size={16} />
        {status.kind === 'busy' ? t('geo.locating') : t('geo.useMine')}
      </button>
      <span role="status" className={`text-xs ${status.kind === 'error' ? 'text-critical' : 'text-ink-2'}`}>
        {status.kind === 'ok' && t('geo.filled', { m: fmt.number(Math.round(status.accuracy)) })}
        {status.kind === 'error' && status.message}
      </span>
    </div>
  )
}
