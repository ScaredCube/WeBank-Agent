import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
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

/**
 * View Transitions reveal the NEW document snapshot from the toggle's corner.
 * The old snapshot stays fixed underneath; no screenshot/canvas is needed.
 * Reduced motion and browsers without View Transitions switch immediately.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialMode)
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme)
  const transitionBusy = useRef(false)
  const resolved = mode === 'system' ? system : mode
  const toggle = useCallback((origin?: { x: number; y: number }) => {
    if (transitionBusy.current) return
    const next: ResolvedTheme = resolved === 'dark' ? 'light' : 'dark'
    const update = () => setMode(next)

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (!origin || reduced || typeof document.startViewTransition !== 'function') {
      update()
      return
    }

    const x = Math.max(0, Math.min(window.innerWidth, origin.x))
    const y = Math.max(0, Math.min(window.innerHeight, origin.y))
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    transitionBusy.current = true
    try {
      const transition = document.startViewTransition(() => {
        // Theme CSS custom properties and the penguin image must both be in the NEW snapshot.
        flushSync(update)
      })
      void transition.ready.then(() => {
        document.documentElement.animate(
          { clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${radius}px at ${x}px ${y}px)`,
          ] },
          {
            duration: 720,
            easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
            fill: 'forwards',
            pseudoElement: '::view-transition-new(root)',
          },
        )
      }).catch(() => { /* navigation/another transition may abort the animation */ })
      void transition.finished.finally(() => { transitionBusy.current = false })
    } catch {
      transitionBusy.current = false
      update()
    }
  }, [resolved])

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
