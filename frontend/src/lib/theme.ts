/** Light or dark appearance (ADR-069). "system" follows the device; the choice is kept in this browser only. */
export type ThemePref = 'system' | 'light' | 'dark'

const KEY = 'gg.theme'

export function readTheme(): ThemePref {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'light' || v === 'dark' ? v : 'system'
  } catch {
    return 'system'
  }
}

/** Sets data-theme on <html>; index.css switches its colour tokens on it. */
export function applyTheme(pref: ThemePref): void {
  const el = document.documentElement
  if (pref === 'system') el.removeAttribute('data-theme')
  else el.setAttribute('data-theme', pref)
}

export function saveTheme(pref: ThemePref): void {
  try {
    if (pref === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, pref)
  } catch {
    /* the choice still applies for this visit */
  }
  applyTheme(pref)
}
