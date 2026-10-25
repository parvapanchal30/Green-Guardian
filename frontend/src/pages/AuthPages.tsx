import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ProblemError } from '../api/client'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { errorMessage } from '../components/states'
import { useT } from '../i18n'
import { useAuth } from '../lib/auth'

function Shell({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center p-4">
      <div className="w-full max-w-sm space-y-5 rounded-lg border border-line bg-surface p-6">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-sm font-semibold tracking-tight text-moss">GreenGuardian</p>
            <h1 className="text-xl font-semibold">{title}</h1>
          </div>
          <LanguageSwitcher />
        </div>
        {children}
        <p className="text-sm text-ink-2">{footer}</p>
      </div>
    </div>
  )
}

function Field({ id, label, error, ...props }: { id: string; label: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-ink-2">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} className="w-full rounded border border-line bg-canvas px-2 py-1.5" {...props} />
      {error && <p id={`${id}-err`} className="mt-1 text-sm text-critical">{error}</p>}
    </div>
  )
}

/** A password box with a button inside it that shows or hides what was typed (the button never submits the form). */
function PasswordField({ id, label, error, ...props }: { id: string; label: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  const t = useT()
  const [shown, setShown] = useState(false)
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm text-ink-2">{label}</label>
      <div className="relative">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-err` : undefined}
          className="w-full rounded border border-line bg-canvas py-1.5 pl-2 pr-16"
          {...props}
        />
        <button
          type="button"
          aria-controls={id}
          aria-pressed={shown}
          aria-label={shown ? t('auth.hidePassword') : t('auth.showPassword')}
          onClick={() => setShown((v) => !v)}
          className="absolute inset-y-0 right-0 flex items-center gap-1 rounded-r px-2 text-xs text-ink-2 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-moss"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
            <circle cx="12" cy="12" r="3" />
            {shown && <path d="M3 3l18 18" />}
          </svg>
          <span aria-hidden="true">{shown ? t('auth.hide') : t('auth.show')}</span>
        </button>
      </div>
      {error && <p id={`${id}-err`} className="mt-1 text-sm text-critical">{error}</p>}
    </div>
  )
}

function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ProblemError)) return {}
  return Object.fromEntries(e.fieldErrors.map((f) => [f.loc[f.loc.length - 1], f.msg]))
}

export function LoginPage() {
  const t = useT()
  const { login, status } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  if (status === 'authed') return <Navigate to="/" replace />

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await login(String(f.get('email')), String(f.get('password')))
      navigate('/')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Shell title={t('auth.signIn')} footer={<>{t('auth.noAccount')} <Link className="text-moss underline" to="/register">{t('auth.createOne')}</Link></>}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field id="email" name="email" type="email" label={t('auth.email')} autoComplete="email" required />
        <PasswordField id="password" name="password" label={t('auth.password')} autoComplete="current-password" required />
        {error != null && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className="w-full rounded bg-moss px-3 py-2 text-moss-ink disabled:opacity-60">{busy ? t('auth.signingIn') : t('auth.signIn')}</button>
      </form>
    </Shell>
  )
}

export function RegisterPage() {
  const t = useT()
  const { register, status } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  if (status === 'authed') return <Navigate to="/" replace />
  const fe = fieldErrors(error)

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const f = new FormData(e.currentTarget)
    setBusy(true)
    setError(null)
    try {
      await register(String(f.get('name')), String(f.get('email')), String(f.get('password')))
      navigate('/')
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Shell title={t('auth.createAccountTitle')} footer={<>{t('auth.alreadyRegistered')} <Link className="text-moss underline" to="/login">{t('auth.signIn')}</Link></>}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field id="name" name="name" label={t('auth.name')} autoComplete="name" required error={fe.name} />
        <Field id="email" name="email" type="email" label={t('auth.email')} autoComplete="email" required error={fe.email} />
        <PasswordField id="password" name="password" label={t('auth.passwordNew')} autoComplete="new-password" required minLength={10} error={fe.password} />
        {error != null && Object.keys(fe).length === 0 && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className="w-full rounded bg-moss px-3 py-2 text-moss-ink disabled:opacity-60">{busy ? t('auth.creating') : t('auth.createAccount')}</button>
      </form>
    </Shell>
  )
}
