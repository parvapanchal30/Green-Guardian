export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const ACCEPTED_TYPES = ['image/jpeg', 'image/png', 'image/webp']

/** Client-side pre-check for a faster message; the server re-validates everything from the bytes. */
export function checkImageFile(file: { type: string; size: number }): string | null {
  if (file.size === 0) return 'That file is empty.'
  if (!ACCEPTED_TYPES.includes(file.type)) return 'Choose a JPEG, PNG or WebP image.'
  if (file.size > MAX_UPLOAD_BYTES) return `That file is ${(file.size / 1048576).toFixed(1)} MB; the limit is 10 MB.`
  return null
}
