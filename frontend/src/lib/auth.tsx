import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

import { api, type User } from '@/lib/api'
import { AuthContext } from '@/lib/auth-context'
import { subscribeUnauthorized } from '@/lib/session'

const TOKEN_KEY = 'bank_agent.token'
const USER_KEY = 'bank_agent.user'

function readStoredUser(): User | null {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState<User | null>(readStoredUser)
  const [sessionVersion, setSessionVersion] = useState(0)
  const currentToken = useRef(token)

  const login = useCallback(async (username: string, password: string) => {
    const result = await api.login(username, password)
    currentToken.current = result.access_token
    localStorage.setItem(TOKEN_KEY, result.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(result.user))
    setToken(result.access_token)
    setUser(result.user)
    setSessionVersion((version) => version + 1)
    return result.user
  }, [])

  const logout = useCallback(() => {
    currentToken.current = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
    setSessionVersion((version) => version + 1)
  }, [])

  useEffect(() => subscribeUnauthorized((expiredToken) => {
    if (currentToken.current && expiredToken === currentToken.current) logout()
  }), [logout])

  const value = useMemo(
    () => ({ token, user, sessionVersion, login, logout }),
    [token, user, sessionVersion, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
