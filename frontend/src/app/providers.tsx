import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { ProblemError } from '../api/client'
import { I18nProvider } from '../i18n'

export function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // never retry client errors (404/403/422): they will not change on retry
        retry: (count, err) => !(err instanceof ProblemError && err.status >= 400 && err.status < 500) && count < 2,
      },
    },
  })
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(makeQueryClient)
  return (
    <I18nProvider>
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    </I18nProvider>
  )
}
