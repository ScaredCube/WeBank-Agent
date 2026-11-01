import { Navigate } from 'react-router-dom'
import { Fragment, type ReactNode } from 'react'

import { useAuth } from '@/lib/use-auth'

export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, sessionVersion } = useAuth()
  if (!token) {
    return <Navigate to="/login" replace />
  }
  return <Fragment key={sessionVersion}>{children}</Fragment>
}
