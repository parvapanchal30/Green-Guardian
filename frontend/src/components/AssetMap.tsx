import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import type { HealthBand, MapFeature } from '../api/types'

/**
 * Leaflet rendering of one point layer. All data arrives from the server; this component only draws it and reports
 * selection. Markers carry a glyph as well as a colour (● healthy, ▲ at risk, ■ critical, ○ no data) so state never
 * relies on colour alone.
 */
const GLYPH: Record<HealthBand | 'none', { glyph: string; cls: string }> = {
  healthy: { glyph: '●', cls: 'text-healthy' },
  at_risk: { glyph: '▲', cls: 'text-at-risk' },
  critical: { glyph: '■', cls: 'text-critical' },
  none: { glyph: '○', cls: 'text-ink-2' },
}

/** Base-map tiles. The public OpenStreetMap server is for light use only: set VITE_MAP_TILE_URL to a provider before production. */
const TILE_URL = import.meta.env.VITE_MAP_TILE_URL ?? 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'

function iconFor(f: MapFeature, selected: boolean) {
  const g = GLYPH[f.properties.health_band ?? 'none']
  const ring = selected ? 'ring-2 ring-ink' : ''
  const badge = f.properties.open_issue_count > 0 ? '<span class="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-critical"></span>' : ''
  return L.divIcon({
    className: '',
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    html: `<span class="relative flex h-7 w-7 items-center justify-center rounded-full border border-line bg-surface text-base leading-none shadow ${g.cls} ${ring}">${g.glyph}${badge}</span>`,
  })
}

export function AssetMap({
  features, bbox, selectedId, onSelect,
}: {
  features: MapFeature[]
  bbox: [number, number, number, number] | null
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const fitted = useRef<string>('')
  const onSelectRef = useRef(onSelect)
  useEffect(() => { onSelectRef.current = onSelect }, [onSelect])

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: true }).setView([20.5, 78.9], 4)
    L.tileLayer(TILE_URL, {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null; layer.current = null }
  }, [])

  useEffect(() => {
    const m = map.current, g = layer.current
    if (!m || !g) return
    g.clearLayers()
    for (const f of features) {
      const [lon, lat] = f.geometry.coordinates
      L.marker([lat, lon], { icon: iconFor(f, f.id === selectedId), title: f.properties.label, keyboard: true, alt: f.properties.label })
        .on('click', () => onSelectRef.current(f.id))
        .addTo(g)
    }
    // Refit only when the set of results changes, so selecting a marker never moves the viewport.
    const key = features.map((f) => f.id).join(',')
    if (bbox && key !== fitted.current) {
      fitted.current = key
      const [w, s, e, n] = bbox
      m.fitBounds([[s, w], [n, e]], { padding: [40, 40], maxZoom: 17 })
    }
  }, [features, bbox, selectedId])

  return <div ref={el} role="application" aria-label="Map of biological assets" className="h-[26rem] w-full rounded-lg border border-line bg-surface-2 lg:h-[34rem]" />
}
