import { translate, type Params, type TKey } from '../i18n'

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Client-side pre-check for a faster message; the server re-validates everything from the bytes. Pass `t` for the
 * current language; without it the message is English. */
export function checkImageFile(
  file: { type: string; size: number },
  t: (key: TKey, params?: Params) => string = (key, params) => translate('en', key, params),
): string | null {
  if (file.size === 0) return t('evidence.fileEmpty')
  if (!ACCEPTED_TYPES.includes(file.type)) return t('evidence.fileType')
  if (file.size > MAX_UPLOAD_BYTES) return t('evidence.fileTooBig', { size: (file.size / 1048576).toFixed(1) })
  return null
}
