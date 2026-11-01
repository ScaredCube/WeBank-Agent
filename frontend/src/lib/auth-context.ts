import { createContext } from 'react'

import type { User } from '@/lib/api'

export interface AuthContextValue {
  token: string | null
  user: User | null
  sessionVersion: number
  login: (username: string, password: string) => Promise<User>
  logout: () => void
}

export const AuthContext = createContext<AuthContextValue | null>(null)
