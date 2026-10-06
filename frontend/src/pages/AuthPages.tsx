import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ProblemError } from '../api/client'
import { errorMessage } from '../components/states'
import { useAuth } from '../lib/auth'

function Shell({ title, children, footer }: { title: string; children: React.ReactNode; footer: React.ReactNode }) {
  return (
    <div className="grid min-h-screen place-items-center p-4">
      <div className="w-full max-w-sm space-y-5 rounded-lg border border-line bg-surface p-6">
        <div>
          <p className="text-sm font-semibold tracking-tight text-moss">GreenGuardian</p>
          <h1 className="text-xl font-semibold">{title}</h1>
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

function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ProblemError)) return {}
  return Object.fromEntries(e.fieldErrors.map((f) => [f.loc[f.loc.length - 1], f.msg]))
}

export function LoginPage() {
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
    <Shell title="Sign in" footer={<>No account? <Link className="text-moss underline" to="/register">Create one</Link></>}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field id="email" name="email" type="email" label="Email" autoComplete="email" required />
        <Field id="password" name="password" type="password" label="Password" autoComplete="current-password" required />
        {error != null && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className="w-full rounded bg-moss px-3 py-2 text-moss-ink disabled:opacity-60">{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </Shell>
  )
}

export function RegisterPage() {
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
    <Shell title="Create your account" footer={<>Already registered? <Link className="text-moss underline" to="/login">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        <Field id="name" name="name" label="Name" autoComplete="name" required error={fe.name} />
        <Field id="email" name="email" type="email" label="Email" autoComplete="email" required error={fe.email} />
        <Field id="password" name="password" type="password" label="Password (10+ characters)" autoComplete="new-password" required minLength={10} error={fe.password} />
        {error != null && Object.keys(fe).length === 0 && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className="w-full rounded bg-moss px-3 py-2 text-moss-ink disabled:opacity-60">{busy ? 'Creating…' : 'Create account'}</button>
      </form>
    </Shell>
  )
}
