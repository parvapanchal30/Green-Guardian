import { describe, expect, it } from 'vitest'
import { ROUTES, navFor, statusLabel } from '../app/routes'

const labels = (mode: Parameters<typeof navFor>[0]) => navFor(mode).flatMap((g) => g.items.map((i) => i.label))

describe('route registry', () => {
  it('has unique paths', () => {
    const paths = ROUTES.map((r) => r.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it('only marks as live what is implemented', () => {
    expect(ROUTES.filter((r) => r.status === 'live').map((r) => r.path).sort()).toEqual(['', 'monitor/weather', 'settings/members'])
  })

  it('every future (soon) surface is gated by a backend capability and names its technique', () => {
    for (const r of ROUTES.filter((r) => r.status === 'soon')) {
      expect(r.capability, r.path).toBeTruthy()
      expect(r.technique, r.path).toBeTruthy()
      expect(r.stage, r.path).toBeTruthy()
    }
  })

  it('is mode-aware without becoming a different product', () => {
    const green = labels('green_management')
    const agri = labels('agricultural_production')
    expect(green).toContain('Survival Prediction')
    expect(green).not.toContain('Crop Recommendation')
    expect(agri).toContain('Crop Recommendation')
    expect(agri).toContain('Harvests')
    expect(green).not.toContain('Harvests')
    // the shared core is identical in both modes
    for (const shared of ['Home', 'All assets', 'Tasks', 'Botanical issues', 'Map', 'Disease Detection', 'Weather']) {
      expect(green).toContain(shared)
      expect(agri).toContain(shared)
    }
  })

  it('labels MVP items "In development" and V2+ items "Coming soon"', () => {
    const tasks = ROUTES.find((r) => r.path === 'tasks')!
    const disease = ROUTES.find((r) => r.path === 'ai/disease-detection')!
    expect(statusLabel(tasks)).toBe('In development')
    expect(statusLabel(disease)).toMatch(/^Coming soon/)
    expect(statusLabel(ROUTES[0])).toBeNull()
  })
})
