// Layout-only previews of planned features. Used inside <ComingSoonPanel>, which disables every control.
// They contain labels and empty controls only; there are no sample values or results.

function Field({ label, placeholder }: { label: string; placeholder: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-ink-2">{label}</span>
      <input className="w-full rounded border border-line bg-canvas px-2 py-1.5" placeholder={placeholder} />
    </label>
  )
}

export function CropPlanningPreview() {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Location" placeholder="Village / district" />
        <Field label="Area" placeholder="acres" />
        <Field label="Soil" placeholder="soil type" />
        <Field label="pH" placeholder="e.g. 6.4" />
        <Field label="Water availability" placeholder="low / moderate / high" />
        <Field label="Season" placeholder="season" />
        <Field label="Market" placeholder="nearest market" />
        <Field label="Budget" placeholder="amount" />
      </div>
      <button type="button" className="rounded bg-moss px-3 py-1.5 text-sm text-moss-ink">
        Generate recommendations
      </button>
    </div>
  )
}

export function DiseaseScanPreview() {
  return (
    <div className="space-y-3">
      <Field label="Select asset" placeholder="Asset" />
      <div className="rounded border border-dashed border-line p-6 text-center text-sm text-ink-2">Upload a plant image</div>
      <div className="flex gap-2">
        <button type="button" className="rounded bg-moss px-3 py-1.5 text-sm text-moss-ink">
          Analyze
        </button>
        <button type="button" className="rounded border border-line px-3 py-1.5 text-sm">
          Create issue
        </button>
      </div>
      <p className="text-xs text-ink-3">Result layout (condition, confidence, severity, affected area) appears here once the model is live.</p>
    </div>
  )
}

export function ForecastPanelPreview({ lines }: { lines: string[] }) {
  return (
    <ul className="space-y-1 text-sm text-ink-2">
      {lines.map((l) => (
        <li key={l}>{l}</li>
      ))}
    </ul>
  )
}

export const PREVIEWS: Record<string, () => React.JSX.Element> = {
  crop_recommendation: CropPlanningPreview,
  disease_detection: DiseaseScanPreview,
}
