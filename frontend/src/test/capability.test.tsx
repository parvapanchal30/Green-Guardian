import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Capability } from '../api/types'
import { CapabilityGate } from '../components/CapabilityGate'
import { CropPlanningPreview } from '../components/previews'

const cap = (over: Partial<Capability>): Capability => ({
  key: 'disease_detection', label: 'Disease Detection', technique: 'Computer vision', stage: 'v2', available: false, reason: 'Planned (V2)', ...over,
})

describe('CapabilityGate', () => {
  it('never renders the live feature when the capability is unavailable', () => {
    render(
      <CapabilityGate feature="disease_detection" capabilities={[cap({})]} title="Disease Detection" preview={<CropPlanningPreview />}>
        <div>LIVE FEATURE</div>
      </CapabilityGate>,
    )
    expect(screen.queryByText('LIVE FEATURE')).not.toBeInTheDocument()
    expect(screen.getByText('Coming soon')).toBeInTheDocument()
    expect(screen.getByText(/Powered by: Computer vision/)).toBeInTheDocument()
    expect(screen.getByText(/No result is computed or displayed/)).toBeInTheDocument()
  })

  it('disables every control inside the preview', () => {
    render(
      <CapabilityGate feature="disease_detection" capabilities={[cap({})]} title="x" preview={<CropPlanningPreview />}>
        <div />
      </CapabilityGate>,
    )
    for (const input of screen.getAllByRole('textbox')) expect(input).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Generate recommendations' })).toBeDisabled()
  })

  it('renders the live feature when the server says it is available', () => {
    render(
      <CapabilityGate feature="disease_detection" capabilities={[cap({ available: true, reason: null })]} title="x">
        <div>LIVE FEATURE</div>
      </CapabilityGate>,
    )
    expect(screen.getByText('LIVE FEATURE')).toBeInTheDocument()
  })

  it('treats an unknown capability as unavailable (fail closed)', () => {
    render(
      <CapabilityGate feature="nope" capabilities={[cap({})]} title="Unknown">
        <div>LIVE FEATURE</div>
      </CapabilityGate>,
    )
    expect(screen.queryByText('LIVE FEATURE')).not.toBeInTheDocument()
    expect(screen.getByText(/Not registered with the server/)).toBeInTheDocument()
  })

  it('shows a loading state, not the feature, while capabilities load', () => {
    render(
      <CapabilityGate feature="disease_detection" capabilities={undefined} title="x">
        <div>LIVE FEATURE</div>
      </CapabilityGate>,
    )
    expect(screen.queryByText('LIVE FEATURE')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })
})
