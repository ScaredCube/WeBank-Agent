import { useCallback, useEffect, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'
import { ThemeContext, type ThemeMode, type ResolvedTheme } from './theme-context'

const STORAGE_KEY = 'webank-agent-theme'

function systemTheme(): ResolvedTheme {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark' : 'light'
}

function initialMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved === 'light' || saved === 'dark' || saved === 'system' ? saved : 'light'
  } catch {
    return 'light'
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialMode)
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme)
  const resolved = mode === 'system' ? system : mode
  const toggle = useCallback(() => setMode(current => {
    const actual = current === 'system' ? system : current
    return actual === 'dark' ? 'light' : 'dark'
  }), [system])

  useEffect(() => {
    if (!window.matchMedia) return
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => setSystem(media.matches ? 'dark' : 'light')
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = resolved
    document.documentElement.style.colorScheme = resolved
    try { localStorage.setItem(STORAGE_KEY, mode) } catch { /* storage can be unavailable */ }
  }, [resolved, mode])

  const value = useMemo(() => ({ mode, resolved, setMode, toggle }), [mode, resolved, toggle])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
