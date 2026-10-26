import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { useI18n } from '../../i18n'

const TILE_URL = import.meta.env.VITE_MAP_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

const pin = L.divIcon({
  className: '',
  iconSize: [30, 40],
  iconAnchor: [15, 38],
  html: '<svg width="30" height="40" viewBox="0 0 30 40" aria-hidden="true"><path d="M15 39C15 39 28 23.5 28 14A13 13 0 0 0 2 14c0 9.5 13 25 13 25z" fill="#2f5d3a" stroke="#fff" stroke-width="2"/><circle cx="15" cy="14" r="5" fill="#fff"/></svg>',
})

/**
 * A map with one pin (ADR-075, "Any place"): drag the pin or click the map to move it; `onMove` reports the new
 * point. The pin is also keyboard-movable through the parent's search and "Use my location"; the map adds precision.
 */
export function PinMap({ lat, lon, zoom, onMove }: { lat: number; lon: number; zoom: number; onMove: (lat: number, lon: number) => void }) {
  const { t } = useI18n()
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marker = useRef<L.Marker | null>(null)
  const onMoveRef = useRef(onMove)
  useEffect(() => {
    onMoveRef.current = onMove
  }, [onMove])

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true }).setView([lat, lon], zoom)
    L.tileLayer(TILE_URL, {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    const mk = L.marker([lat, lon], { draggable: true, icon: pin, keyboard: true, title: t('weather.pin') }).addTo(m)
    mk.on('dragend', () => {
      const p = mk.getLatLng()
      onMoveRef.current(p.lat, p.lng)
    })
    m.on('click', (e: L.LeafletMouseEvent) => {
      mk.setLatLng(e.latlng)
      onMoveRef.current(e.latlng.lat, e.latlng.lng)
    })
    const ro = new ResizeObserver(() => m.invalidateSize())
    ro.observe(el.current)
    map.current = m
    marker.current = mk
    return () => {
      ro.disconnect()
      m.remove()
      map.current = null
      marker.current = null
    }
    // Created once; later positions arrive through the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const m = map.current
    const mk = marker.current
    if (!m || !mk) return
    const here = mk.getLatLng()
    if (Math.abs(here.lat - lat) > 1e-6 || Math.abs(here.lng - lon) > 1e-6) {
      mk.setLatLng([lat, lon])
      m.setView([lat, lon], Math.max(m.getZoom(), zoom))
    }
  }, [lat, lon, zoom])

  return <div ref={el} className="h-full min-h-[320px] w-full" role="application" aria-label={t('weather.mapLabel')} />
}
