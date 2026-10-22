import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TourButton, TourPanel } from '../components/TourPanel'
import { en } from '../i18n/catalog.en'
import { hi } from '../i18n/catalog.hi'
import { STEPS, stepsFor } from '../tour/steps'

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>
}

function renderPanel(over: Partial<React.ComponentProps<typeof TourPanel>> = {}, page: React.ReactNode = <main><h1>Dashboard</h1></main>) {
  const onClose = vi.fn()
  const view = render(
    <MemoryRouter initialEntries={['/w/w1']}>
      {page}
      <Where />
      <TourPanel ws="w1" mode="green_management" role="manager" onClose={onClose} {...over} />
    </MemoryRouter>,
  )
  return { onClose, ...view }
}

afterEach(() => {
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('which steps a person sees', () => {
  it('shows only what the role and the mode make meaningful', () => {
    const ids = (mode: 'green_management' | 'agricultural_production', role: 'viewer' | 'manager') => stepsFor(mode, role).map((s) => s.id)
    expect(ids('green_management', 'viewer')).not.toContain('audit')
    expect(ids('green_management', 'manager')).toContain('audit')
    expect(ids('green_management', 'manager')).not.toContain('asset-harvests')
    expect(ids('agricultural_production', 'viewer')).toContain('asset-harvests')
  })

  it('has unique ids, and a title and caption in English and Hindi for every step', () => {
    expect(new Set(STEPS.map((s) => s.id)).size).toBe(STEPS.length)
    for (const catalog of [en, hi] as Record<string, string>[]) {
      for (const s of STEPS) {
        expect(catalog[`tour.step.${s.id}.title`]?.length, `${s.id} title`).toBeGreaterThanOrEqual(3)
        expect(catalog[`tour.step.${s.id}.caption`]?.length, `${s.id} caption`).toBeGreaterThan(30)
      }
    }
  })
})

describe('tour panel', () => {
  it('starts on the dashboard and moves through the steps with Next and Back', async () => {
    renderPanel()
    expect(screen.getByText(/Step 1 of /)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Your workspace at a glance' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Back' })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.getByRole('heading', { name: 'Assets and their lifecycle stage' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/w/w1/assets'))
    await userEvent.click(screen.getByRole('button', { name: 'Back' }))
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent(/^\/w\/w1$/))
  })

  it('highlights the element being explained and clears it when it closes', async () => {
    // the page lives outside the panel's React tree, as the real pages do relative to the panel
    const page = document.createElement('main')
    const heading = document.createElement('h1')
    heading.textContent = 'Dashboard'
    page.append(heading)
    document.body.append(page)
    const { unmount } = renderPanel({}, <></>)
    await waitFor(() => expect(heading).toHaveAttribute('data-tour-focus'))
    expect(heading.style.outline).toContain('solid')
    unmount()
    expect(heading).not.toHaveAttribute('data-tour-focus')
    expect(heading.style.outline).toBe('')
  })

  it('opens the first asset for asset steps', async () => {
    const page = (
      <main>
        <h1>Assets</h1>
        <table><tbody><tr><td><a href="/w/w1/assets/abc">Neem</a></td></tr></tbody></table>
      </main>
    )
    renderPanel({ role: 'viewer' }, page)
    await userEvent.click(screen.getByRole('button', { name: 'Next' })) // assets
    await userEvent.click(screen.getByRole('button', { name: 'Next' })) // first asset
    await waitFor(() => expect(screen.getByTestId('where')).toHaveTextContent('/w/w1/assets/abc'))
  })

  it('says so, instead of failing, when there is nothing to show for a step', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderPanel({}, <main />) // no h1 on the page
    await act(async () => {
      await vi.advanceTimersByTimeAsync(7000)
    })
    expect(screen.getByRole('status')).toHaveTextContent(/nothing to show for this step/i)
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
  })

  it('finishes on the last step, and Close and Escape both end it', async () => {
    const first = renderPanel({ role: 'viewer' })
    for (let i = 0; i < stepsFor('green_management', 'viewer').length - 1; i++) await userEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Finish' }))
    expect(first.onClose).toHaveBeenCalledTimes(1)
    first.unmount()

    const second = renderPanel()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(second.onClose).toHaveBeenCalledTimes(1)
    second.unmount()

    const third = renderPanel()
    await userEvent.keyboard('{Escape}')
    expect(third.onClose).toHaveBeenCalledTimes(1)
  })
})

describe('tour button', () => {
  it('opens the tour on demand and closes it again', async () => {
    render(
      <MemoryRouter initialEntries={['/w/w1']}>
        <main><h1>Dashboard</h1></main>
        <TourButton ws="w1" mode="green_management" role="worker" />
      </MemoryRouter>,
    )
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Take the tour' }))
    expect(screen.getByRole('dialog', { name: 'Product tour' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
