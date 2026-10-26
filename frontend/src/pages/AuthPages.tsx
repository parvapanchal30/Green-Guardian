import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { ProblemError } from '../api/client'
import { Icon } from '../components/icons'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { errorMessage } from '../components/states'
import { useT } from '../i18n'
import { useAuth } from '../lib/auth'

/**
 * Sign-in and registration frame (ADR-074): a green panel that says what GreenGuardian is (wide screens only; on a
 * phone the form comes first with the name above it), and the form. The panel holds no example records.
 */
function Shell({ title, intro, children, footer }: { title: string; intro?: string; children: React.ReactNode; footer: React.ReactNode }) {
  const t = useT()
  return (
    <div className="flex min-h-screen bg-canvas">
      <section aria-label={t('auth.about')} className="hidden w-[min(560px,42vw)] shrink-0 flex-col gap-7 bg-forest px-12 py-12 text-forest-ink lg:flex">
        <Brand onDark />
        <p className="max-w-[14ch] font-display text-[44px] leading-[1.1] font-bold text-white">{t('auth.tagline')}</p>
        <p className="max-w-[40ch] text-[17px] leading-relaxed text-forest-muted">{t('auth.pitch')}</p>
      </section>
      <main className="flex min-w-0 flex-1 flex-col px-4 py-6 sm:px-12 sm:py-8">
        <div className="flex items-center justify-between gap-3">
          <span className="lg:hidden"><Brand /></span>
          <LanguageSwitcher className="ml-auto bg-surface" />
        </div>
        <div className="my-auto w-full max-w-[400px] self-center py-8">
          <h1 className="text-[34px] leading-tight font-bold">{title}</h1>
          {intro && <p className="mt-1 text-ink-2">{intro}</p>}
          <div className="mt-6">{children}</div>
          <div className="mt-5 flex flex-wrap justify-between gap-x-4 gap-y-1 text-sm">{footer}</div>
        </div>
      </main>
    </div>
  )
}

function Brand({ onDark = false }: { onDark?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <span className={`flex h-9 w-9 items-center justify-center rounded-md ${onDark ? 'bg-forest-ink text-forest' : 'bg-moss text-moss-ink'}`}>
        <Icon name="comingNext" size={20} />
      </span>
      <span className={`font-display text-2xl font-bold ${onDark ? 'text-forest-ink' : 'text-ink'}`}>GreenGuardian</span>
    </span>
  )
}

const inputCls = 'w-full rounded-md border border-line bg-surface px-3 py-2.5 text-[15px]'

function Field({ id, label, error, ...props }: { id: string; label: string; error?: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold">{label}</label>
      <input id={id} aria-invalid={!!error} aria-describedby={error ? `${id}-err` : undefined} className={inputCls} {...props} />
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
      <label htmlFor={id} className="mb-1.5 block text-sm font-semibold">{label}</label>
      <div className="relative">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          aria-invalid={!!error}
          aria-describedby={error ? `${id}-err` : undefined}
          className={`${inputCls} pr-24`}
          {...props}
        />
        <button
          type="button"
          aria-controls={id}
          aria-pressed={shown}
          aria-label={shown ? t('auth.hidePassword') : t('auth.showPassword')}
          onClick={() => setShown((v) => !v)}
          className="absolute inset-y-1 right-1 flex items-center gap-1.5 rounded px-2.5 text-sm font-semibold text-moss hover:bg-surface-2 focus-visible:outline-2 focus-visible:outline-moss"
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

const submitCls = 'h-12 w-full rounded-md bg-moss px-3 text-base font-semibold text-moss-ink hover:opacity-90 disabled:opacity-60'

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
    <Shell
      title={t('auth.signIn')}
      intro={t('auth.signInIntro')}
      footer={
        <>
          <span>{t('auth.noAccount')} <Link className="font-semibold text-moss underline" to="/register">{t('auth.createOne')}</Link></span>
          <span className="text-ink-2">{t('auth.forgot')}</span>
        </>
      }
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field id="email" name="email" type="email" label={t('auth.email')} autoComplete="email" required />
        <PasswordField id="password" name="password" label={t('auth.password')} autoComplete="current-password" required />
        {error != null && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className={submitCls}>{busy ? t('auth.signingIn') : t('auth.signIn')}</button>
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
    <Shell
      title={t('auth.createAccountTitle')}
      intro={t('auth.registerIntro')}
      footer={<span>{t('auth.alreadyRegistered')} <Link className="font-semibold text-moss underline" to="/login">{t('auth.signIn')}</Link></span>}
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field id="name" name="name" label={t('auth.name')} autoComplete="name" required error={fe.name} />
        <Field id="email" name="email" type="email" label={t('auth.email')} autoComplete="email" required error={fe.email} />
        <PasswordField id="password" name="password" label={t('auth.passwordNew')} autoComplete="new-password" required minLength={10} error={fe.password} />
        {error != null && Object.keys(fe).length === 0 && <p role="alert" className="text-sm text-critical">{errorMessage(error)}</p>}
        <button disabled={busy} className={submitCls}>{busy ? t('auth.creating') : t('auth.createAccount')}</button>
      </form>
    </Shell>
  )
}
