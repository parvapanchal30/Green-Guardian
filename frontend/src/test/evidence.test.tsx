import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api, apiBlob, configureApi, tokenStore } from '../api/client'
import type { Evidence } from '../api/types'
import { checkImageFile } from '../lib/evidence'

const state = vi.hoisted(() => ({
  list: {} as Record<string, unknown>,
  blob: {} as Record<string, unknown>,
  upload: vi.fn(),
  remove: vi.fn(),
  userId: 'u1' as string | undefined,
}))

vi.mock('../lib/auth', () => ({ useAuth: () => ({ user: state.userId ? { id: state.userId } : null }) }))
vi.mock('../lib/slice', () => ({
  useEvidence: () => state.list,
  useEvidenceBlob: () => state.blob,
  useUploadEvidence: () => ({ mutate: state.upload, reset: vi.fn(), isPending: false, error: null }),
  useDeleteEvidence: () => ({ mutate: state.remove, isPending: false, error: null }),
}))

import { EvidenceGallery } from '../components/EvidenceGallery'

const ev = (id: string, over: Partial<Evidence> = {}): Evidence => ({
  id, asset_id: 'a1', observation_id: null, issue_id: null, uploaded_by: 'u1', original_filename: `${id}.jpg`, content_type: 'image/jpeg',
  size_bytes: 2048, sha256: 'x'.repeat(64), width: 640, height: 480, caption: `Photo ${id}`, created_at: '2026-10-17T10:00:00Z',
  content_path: `/workspaces/w1/evidence/${id}/content`, ...over,
})
const file = (name: string, type: string, size = 100) => new File([new Uint8Array(size)], name, { type })

describe('checkImageFile', () => {
  it('accepts supported images and explains every rejection', () => {
    expect(checkImageFile({ type: 'image/png', size: 10 })).toBeNull()
    expect(checkImageFile({ type: 'image/webp', size: 10 })).toBeNull()
    expect(checkImageFile({ type: 'image/gif', size: 10 })).toMatch(/JPEG, PNG or WebP/)
    expect(checkImageFile({ type: 'application/pdf', size: 10 })).toMatch(/JPEG, PNG or WebP/)
    expect(checkImageFile({ type: 'image/jpeg', size: 11 * 1024 * 1024 })).toMatch(/limit is 10 MB/)
    expect(checkImageFile({ type: 'image/jpeg', size: 0 })).toMatch(/empty/)
  })
})

describe('api client multipart and blobs', () => {
  beforeEach(() => { configureApi({ baseUrl: '/api/v1' }); tokenStore.setTokens({ access_token: 'acc', refresh_token: 'ref', token_type: 'bearer', expires_in: 900 }) })
  afterEach(() => { vi.unstubAllGlobals(); tokenStore.clear() })

  it('sends FormData untouched (no JSON content type, no stringify) with the bearer token', async () => {
    const f = vi.fn(async () => new Response('{"id":"e1"}', { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', f)
    const form = new FormData()
    form.set('asset_id', 'a1')
    await api('/workspaces/w1/evidence', { method: 'POST', body: form })
    const [, init] = f.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.body).toBe(form)
    const headers = init.headers as Headers
    expect(headers.get('Content-Type')).toBeNull() // the browser adds multipart/form-data with its boundary
    expect(headers.get('Authorization')).toBe('Bearer acc')
  })

  it('fetches protected images as blobs and reports failures as problems', async () => {
    // A string body keeps the test independent of jsdom's Blob vs Node's (undici) Blob, which differ across Node versions.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('img', { status: 200, headers: { 'Content-Type': 'image/png' } })))
    const blob = await apiBlob('/workspaces/w1/evidence/e1/content')
    expect(blob.size).toBe(3)
    expect(blob.type).toBe('image/png')
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"code":"evidence_not_found","detail":"gone"}', { status: 404, headers: { 'Content-Type': 'application/json' } })))
    await expect(apiBlob('/x')).rejects.toMatchObject({ status: 404, code: 'evidence_not_found' })
  })
})

describe('EvidenceGallery', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:fake'), revokeObjectURL: vi.fn() }))
    state.upload.mockReset()
    state.remove.mockReset()
    state.userId = 'u1'
    state.blob = { data: new Blob(['x'], { type: 'image/jpeg' }), error: null, refetch: vi.fn() }
    state.list = { isLoading: false, error: null, data: undefined, refetch: vi.fn() }
  })
  afterEach(() => vi.unstubAllGlobals())

  const show = (props: Partial<Parameters<typeof EvidenceGallery>[0]> = {}) =>
    render(<EvidenceGallery ws="w1" assetId="a1" canUpload isManager={false} {...props} />)

  it('shows loading and error states', () => {
    state.list = { ...state.list, isLoading: true }
    const { unmount } = show()
    expect(screen.getByText(/loading photos/i)).toBeInTheDocument()
    unmount()
    state.list = { ...state.list, isLoading: false, error: new Error('boom') }
    show()
    expect(screen.getByRole('button', { name: /retry|try again/i })).toBeInTheDocument()
  })

  it('explains the empty state differently for people who can and cannot upload', () => {
    state.list = { ...state.list, data: { items: [], total: 0 } }
    const { unmount } = show()
    expect(screen.getByText('No photos yet')).toBeInTheDocument()
    expect(screen.getByText(/upload a photo to keep visual evidence/i)).toBeInTheDocument()
    expect(screen.getByRole('form', { name: 'Upload photo' })).toBeInTheDocument()
    unmount()
    show({ canUpload: false })
    expect(screen.getByText('No photos have been added.')).toBeInTheDocument()
    expect(screen.queryByRole('form', { name: 'Upload photo' })).not.toBeInTheDocument()
  })

  it('populated: shows protected images, opens a viewer, and only offers removal to the uploader or a manager', async () => {
    state.list = { ...state.list, data: { items: [ev('e1'), ev('e2', { uploaded_by: 'someone-else' })], total: 2 } }
    show()
    expect(screen.getAllByRole('img')).toHaveLength(2)

    await userEvent.click(screen.getByRole('button', { name: 'Open photo: Photo e1' }))
    expect(screen.getByRole('dialog', { name: 'Photo' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Remove photo' })) // own upload
    expect(state.remove).toHaveBeenCalledWith('e1', expect.anything())

    await userEvent.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: 'Open photo: Photo e2' }))
    expect(screen.queryByRole('button', { name: 'Remove photo' })).not.toBeInTheDocument() // someone else's, not a manager
  })

  it('managers can remove anyone\'s photo', async () => {
    state.list = { ...state.list, data: { items: [ev('e2', { uploaded_by: 'someone-else' })], total: 1 } }
    show({ isManager: true })
    await userEvent.click(screen.getByRole('button', { name: 'Open photo: Photo e2' }))
    expect(screen.getByRole('button', { name: 'Remove photo' })).toBeInTheDocument()
  })

  it('the uploader rejects unsupported files on the client and uploads valid ones with their links', async () => {
    state.list = { ...state.list, data: { items: [], total: 0 } }
    show({ issueOptions: [{ id: 'i1', label: 'GG-001 · Leaf yellowing' }] })
    const input = screen.getByLabelText(/^Photo/) as HTMLInputElement

    await userEvent.upload(input, file('notes.pdf', 'application/pdf'), { applyAccept: false })
    await userEvent.click(screen.getByRole('button', { name: 'Upload photo' }))
    expect(screen.getByRole('alert')).toHaveTextContent(/JPEG, PNG or WebP/)
    expect(state.upload).not.toHaveBeenCalled()

    await userEvent.upload(input, file('leaf.jpg', 'image/jpeg'))
    await userEvent.type(screen.getByLabelText(/Caption/), 'Lower leaves')
    await userEvent.selectOptions(screen.getByLabelText(/Attach to issue/), 'i1')
    await userEvent.click(screen.getByRole('button', { name: 'Upload photo' }))
    expect(state.upload).toHaveBeenCalledTimes(1)
    expect(state.upload.mock.calls[0][0]).toMatchObject({ assetId: 'a1', caption: 'Lower leaves', issueId: 'i1' })
  })

  it('shows a retry when an image cannot be loaded', () => {
    state.blob = { data: undefined, error: new Error('x'), refetch: vi.fn() }
    state.list = { ...state.list, data: { items: [ev('e1')], total: 1 } }
    show({ canUpload: false })
    expect(screen.getAllByText(/could not load/i).length).toBeGreaterThan(0)
  })
})
