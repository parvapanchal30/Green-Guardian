import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const auth = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }))
vi.mock('../lib/auth', () => ({ useAuth: () => ({ status: 'anon', login: auth.login, register: auth.register }) }))

import { I18nProvider } from '../i18n'
import { LoginPage, RegisterPage } from '../pages/AuthPages'

beforeEach(() => {
  auth.login.mockReset()
  auth.register.mockReset()
})

describe('show or hide the password', () => {
  it('reveals and hides what was typed without submitting the form', async () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    const box = screen.getByLabelText('Password') as HTMLInputElement
    await userEvent.type(box, 'GreenDemo-Owner-2026')
    expect(box.type).toBe('password')
    const toggle = screen.getByRole('button', { name: 'Show password' })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    await userEvent.click(toggle)
    expect(box.type).toBe('text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute('aria-pressed', 'true')
    expect(box.value).toBe('GreenDemo-Owner-2026')
    await userEvent.click(screen.getByRole('button', { name: 'Hide password' }))
    expect(box.type).toBe('password')
    expect(auth.login).not.toHaveBeenCalled() // the toggle is not a submit button
  })

  it('signs in with the typed password whether it is shown or hidden', async () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    await userEvent.type(screen.getByLabelText('Email'), 'demo.owner@example.com')
    await userEvent.type(screen.getByLabelText('Password'), 'GreenDemo-Owner-2026')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(auth.login).toHaveBeenCalledWith('demo.owner@example.com', 'GreenDemo-Owner-2026')
  })

  it('is on the registration page too, and speaks Hindi', async () => {
    render(<I18nProvider initial="hi"><MemoryRouter><RegisterPage /></MemoryRouter></I18nProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'पासवर्ड दिखाएँ' }))
    expect(screen.getByRole('button', { name: 'पासवर्ड छिपाएँ' })).toHaveAttribute('aria-pressed', 'true')
  })
})
