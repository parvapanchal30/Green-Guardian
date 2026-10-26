import { Link } from 'react-router-dom'
import { ROUTES, pathFor, routeKey } from '../app/routes'
import { useWorkspaceCtx } from '../app/WorkspaceLayout'
import { PageHeader } from '../components/domain'
import { LoadingBlock } from '../components/states'
import { StatusChip } from '../components/StatusChip'
import { Card } from '../components/ui'
import { useI18n } from '../i18n'

/**
 * Every capability, live or planned, in one place (it replaces the "Soon" entries that used to fill the menu, and
 * the capability table on Home). Planned features show no results anywhere until they are built and checked.
 */
export function ComingNextPage() {
  const { ws, workspace, capabilities } = useWorkspaceCtx()
  const { t } = useI18n()
  const pageFor = (key: string) => ROUTES.find((r) => r.capability === key && (!r.modes || r.modes.includes(workspace.mode)))
  const sorted = [...(capabilities ?? [])].sort((a, b) => Number(b.available) - Number(a.available) || a.stage.localeCompare(b.stage))

  return (
    <div>
      <PageHeader eyebrow={t('cn.eyebrow')} title={t('cn.title')} subtitle={t('cn.subtitle')} />
      {!capabilities ? (
        <LoadingBlock label={t('dash.loadingCapabilities')} />
      ) : (
        <Card className="relative overflow-x-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{t('dash.capabilitiesCaption')}</caption>
            <thead className="border-b border-line font-mono text-[10.5px] tracking-[0.06em] text-ink-2 uppercase">
              <tr>
                <th className="px-4 py-2.5 font-medium">{t('dash.cap.capability')}</th>
                <th className="px-4 py-2.5 font-medium">{t('dash.cap.technique')}</th>
                <th className="px-4 py-2.5 font-medium">{t('dash.cap.status')}</th>
                <th className="px-4 py-2.5 font-medium"><span className="sr-only">{t('cn.page')}</span></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((cap) => {
                const page = pageFor(cap.key)
                return (
                  <tr key={cap.key} className="border-b border-line-soft last:border-0">
                    <td className="px-4 py-3 font-semibold">{cap.label}</td>
                    <td className="px-4 py-3 text-ink-2">{cap.technique}</td>
                    <td className="px-4 py-3">
                      {cap.available ? (
                        <StatusChip tone="live">{t('dash.cap.live')}</StatusChip>
                      ) : (
                        <StatusChip tone={cap.stage === 'mvp' ? 'building' : 'soon'}>
                          {cap.stage === 'mvp' ? t('dash.cap.inDevelopment') : t('dash.cap.planned', { stage: cap.stage.toUpperCase() })}
                        </StatusChip>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {page && <Link to={pathFor(ws, page)} className="text-moss underline">{t(routeKey(page))}</Link>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
