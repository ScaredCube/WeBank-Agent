import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { DURATION } from '@/lib/motion'
import { ThemeContext, type ThemeMode, type ResolvedTheme } from './theme-context'

const STORAGE_KEY = 'webank-agent-theme'
const THEME_REVEAL_MS = DURATION.theme * 1000

type ViewTransitionDocument = Document & {
  startViewTransition?: (callback: () => void) => {
    ready: Promise<void>
    finished: Promise<void>
  }
}

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

/** Theme switches use a short circular reveal when the browser supports it. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(initialMode)
  const [system, setSystem] = useState<ResolvedTheme>(systemTheme)
  const resolved = mode === 'system' ? system : mode
  const transitioning = useRef(false)
  const toggle = useCallback((origin?: { x: number; y: number }) => {
    const next = resolved === 'dark' ? 'light' : 'dark'
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches ?? false
    const startViewTransition = (document as ViewTransitionDocument).startViewTransition
    if (!startViewTransition || reduced || transitioning.current) {
      setMode(next)
      return
    }
    transitioning.current = true
    const x = origin?.x ?? window.innerWidth
    const y = origin?.y ?? 0
    const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))
    const transition = startViewTransition.call(document, () => {
      flushSync(() => setMode(next))
    })
    transition.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        {
          duration: THEME_REVEAL_MS,
          easing: 'cubic-bezier(0.23, 1, 0.32, 1)',
          pseudoElement: '::view-transition-new(root)',
        },
      )
    }).catch(() => { /* the transition can be skipped by the browser */ })
    transition.finished.finally(() => { transitioning.current = false })
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
