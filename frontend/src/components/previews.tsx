// Layout-only previews of planned features. Used inside <ComingSoonPanel>, which disables every control.
// They contain labels and empty controls only; there are no sample values or results.
import { useI18n } from '../i18n'

function Field({ label, placeholder }: { label: string; placeholder: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block text-ink-2">{label}</span>
      <input className="w-full rounded border border-line bg-canvas px-2 py-1.5" placeholder={placeholder} />
    </label>
  )
}

export function CropPlanningPreview() {
  const { t } = useI18n()
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label={t('preview.location')} placeholder={t('preview.locationPh')} />
        <Field label={t('preview.area')} placeholder={t('preview.areaPh')} />
        <Field label={t('preview.soil')} placeholder={t('preview.soilPh')} />
        <Field label={t('preview.ph')} placeholder={t('preview.phPh')} />
        <Field label={t('preview.water')} placeholder={t('preview.waterPh')} />
        <Field label={t('preview.season')} placeholder={t('preview.seasonPh')} />
        <Field label={t('preview.market')} placeholder={t('preview.marketPh')} />
        <Field label={t('preview.budget')} placeholder={t('preview.budgetPh')} />
      </div>
      <button type="button" className="rounded bg-moss px-3 py-1.5 text-sm text-moss-ink">
        {t('preview.generate')}
      </button>
    </div>
  )
}

export function DiseaseScanPreview() {
  const { t } = useI18n()
  return (
    <div className="space-y-3">
      <Field label={t('preview.selectAsset')} placeholder={t('preview.asset')} />
      <div className="rounded border border-dashed border-line p-6 text-center text-sm text-ink-2">{t('preview.upload')}</div>
      <div className="flex gap-2">
        <button type="button" className="rounded bg-moss px-3 py-1.5 text-sm text-moss-ink">
          {t('preview.analyze')}
        </button>
        <button type="button" className="rounded border border-line px-3 py-1.5 text-sm">
          {t('preview.createIssue')}
        </button>
      </div>
      <p className="text-xs text-ink-3">{t('preview.resultNote')}</p>
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
