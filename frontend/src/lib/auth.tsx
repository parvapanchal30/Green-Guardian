import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, configureApi, refreshSession, tokenStore } from '../api/client'
import type { TokenPair, User } from '../api/types'

type Status = 'loading' | 'anon' | 'authed'

interface AuthValue {
  status: Status
  user: User | null
  login(email: string, password: string): Promise<void>
  register(name: string, email: string, password: string): Promise<void>
  logout(): Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<User | null>(null)

  const lose = useCallback(() => {
    setUser(null)
    setStatus('anon')
  }, [])

  useEffect(() => {
    configureApi({ onAuthLost: lose })
    let cancelled = false
    ;(async () => {
      if (!tokenStore.refresh) return !cancelled && lose()
      try {
        await refreshSession()
        const me = await api<User>('/me')
        if (!cancelled) {
          setUser(me)
          setStatus('authed')
        }
      } catch {
        if (!cancelled) lose()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [lose])

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api<TokenPair>('/auth/login', { method: 'POST', body: { email, password }, auth: false })
    tokenStore.setTokens(tokens)
    setUser(await api<User>('/me'))
    setStatus('authed')
  }, [])

  const register = useCallback(
    async (name: string, email: string, password: string) => {
      await api<User>('/auth/register', { method: 'POST', body: { name, email, password }, auth: false })
      await login(email, password)
    },
    [login],
  )

  const logout = useCallback(async () => {
    const rt = tokenStore.refresh
    if (rt) await api('/auth/logout', { method: 'POST', body: { refresh_token: rt }, auth: false }).catch(() => {})
    tokenStore.clear()
    lose()
  }, [lose])

  const value = useMemo(() => ({ status, user, login, register, logout }), [status, user, login, register, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
