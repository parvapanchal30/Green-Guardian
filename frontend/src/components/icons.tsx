import { ICONS, type IconName } from './icon-set'

export { ICONS, type IconName }

/** A decorative icon from the app's set; see icon-set.ts. */
export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  const Glyph = ICONS[name]
  return <Glyph aria-hidden="true" focusable="false" width={size} height={size} strokeWidth={1.8} className={className} />
}
