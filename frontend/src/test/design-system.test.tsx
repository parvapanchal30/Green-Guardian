import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { PageHeader } from '../components/domain'
import { ICONS } from '../components/icon-set'
import { Icon } from '../components/icons'
import { StatusChip, type Tone } from '../components/StatusChip'
import { EmptyState } from '../components/states'
import { HealthBar, Segmented, StatTile, Tag } from '../components/ui'
import { I18nProvider } from '../i18n'

const css = readFileSync(join(process.cwd(), 'src', 'index.css'), 'utf8')
const fonts = readFileSync(join(process.cwd(), 'src', 'styles', 'fonts.ts'), 'utf8')

function tokens(startMarker: string): Record<string, string> {
  const start = css.indexOf(startMarker)
  const block = css.slice(start, css.indexOf('}', start))
  return Object.fromEntries([...block.matchAll(/--color-([\w-]+):\s*(#[0-9a-f]{6})/g)].map((m) => [m[1], m[2]]))
}
function luminance(hex: string) {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

describe('design tokens', () => {
  const themes = { light: tokens('@theme'), dark: tokens(':root[data-theme="dark"]') }

  it.each(Object.entries(themes))('every text colour reaches 4.5:1 on every background (%s)', (_name, t) => {
    const text = ['ink', 'ink-2', 'ink-3', 'moss', 'soil', 'healthy', 'at-risk', 'critical', 'soon', 'info']
    for (const fg of text) for (const bg of ['canvas', 'surface', 'surface-2']) expect(contrast(t[fg], t[bg]), `${fg} on ${bg}`).toBeGreaterThanOrEqual(4.5)
    for (const s of ['healthy', 'at-risk', 'critical', 'info', 'moss']) expect(contrast(t[s], t[`${s}-soft`]), `${s} chip`).toBeGreaterThanOrEqual(4.5)
    expect(contrast(t['moss-ink'], t.moss), 'primary button').toBeGreaterThanOrEqual(4.5)
  })

  it('dark mode defines the same tokens for the device setting and for an explicit choice', () => {
    expect(tokens(':root:not([data-theme="light"])')).toEqual(themes.dark)
    expect(Object.keys(themes.dark).sort()).toEqual(Object.keys(themes.light).sort())
  })

  it('the app entry loads the bundled fonts before the styles', () => {
    const main = readFileSync(join(process.cwd(), 'src', 'main.tsx'), 'utf8')
    expect(main.indexOf("import './styles/fonts'")).toBeGreaterThan(-1)
    expect(main.indexOf("import './styles/fonts'")).toBeLessThan(main.indexOf("import './index.css'"))
  })

  it('headings take Hindi letters from Martel (the slab face has none) and only its Devanagari subset is bundled', () => {
    expect(css).toMatch(/--font-display:\s*"Zilla Slab",\s*"Martel"/)
    const martel = [...fonts.matchAll(/@fontsource\/martel\/([\w-]+)\.css/g)].map((m) => m[1])
    expect(martel).toEqual(['devanagari-700'])
    expect(fonts).toMatch(/@fontsource\/hind\/devanagari-400\.css/)
  })
})

describe('building blocks', () => {
  it('icons are decorative and every navigation area has one', () => {
    const { container } = render(<Icon name="issues" />)
    expect(container.querySelector('svg')).toHaveAttribute('aria-hidden', 'true')
    for (const name of ['today', 'assets', 'species', 'zones', 'tasks', 'issues', 'inspections', 'health', 'map', 'weather', 'agent', 'reports', 'datasets', 'protocols', 'comingNext', 'settings'])
      expect(ICONS).toHaveProperty(name)
  })

  it('a status chip always carries a shape and its text, never colour alone', () => {
    const tones: Tone[] = ['healthy', 'at-risk', 'critical', 'soon', 'building', 'live', 'neutral', 'info']
    const glyphs = tones.map((tone) => {
      const { container, unmount } = render(<StatusChip tone={tone}>Label</StatusChip>)
      const glyph = container.querySelector('[aria-hidden="true"]')!.textContent
      expect(container).toHaveTextContent('Label')
      unmount()
      return glyph
    })
    expect(new Set(glyphs.slice(0, 3)).size).toBe(3) // healthy, at risk and critical differ in shape
  })

  it('the page header shows the menu group above the title', () => {
    render(<PageHeader eyebrow="Plants" title="Species" subtitle="The shared catalog" />)
    expect(screen.getByRole('heading', { level: 1, name: 'Species' })).toBeInTheDocument()
    expect(screen.getByText('Plants')).toBeInTheDocument()
  })

  it('a segmented control reports the chosen option and calls back with the new one', async () => {
    const onChange = vi.fn()
    render(
      <Segmented
        label="Show"
        value="open"
        onChange={onChange}
        options={[
          { value: 'open', label: 'All open', count: 4 },
          { value: 'mine', label: 'Mine', count: 0 },
        ]}
      />,
    )
    const group = screen.getByRole('group', { name: 'Show' })
    expect(within(group).getByRole('button', { name: /All open/ })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(within(group).getByRole('button', { name: /Mine/ }))
    expect(onChange).toHaveBeenCalledWith('mine')
  })

  it('the health bar sums up the bands in words and draws only bands that have plants', () => {
    const { container } = render(<HealthBar healthy={5} atRisk={0} critical={1} />)
    expect(screen.getByRole('img')).toHaveAccessibleName('5 Healthy, 0 At risk, 1 Critical')
    expect(container.querySelectorAll('[role="img"] > span')).toHaveLength(2)
  })

  it('the health bar speaks Hindi', () => {
    render(
      <I18nProvider initial="hi">
        <HealthBar healthy={2} atRisk={1} critical={0} />
      </I18nProvider>,
    )
    expect(screen.getByRole('img').getAttribute('aria-label')).not.toMatch(/Healthy/)
  })

  it('a stat tile shows its label, value and basis; a tag shows a key', () => {
    render(
      <>
        <StatTile label="Survival" value="85.7%" note="6 alive, 1 died" tone="healthy" />
        <Tag tone="critical">GG-001</Tag>
      </>,
    )
    expect(screen.getByText('85.7%')).toBeInTheDocument()
    expect(screen.getByText('6 alive, 1 died')).toBeInTheDocument()
    expect(screen.getByText('GG-001')).toBeInTheDocument()
  })

  it('an empty state can lead with an icon', () => {
    const { container } = render(<EmptyState icon="datasets" title="No datasets yet" />)
    expect(container.querySelector('svg')).toBeInTheDocument()
    expect(screen.getByText('No datasets yet')).toBeInTheDocument()
  })
})
