import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'

type PrivacyValue = {
  hidden: boolean
  toggle: () => void
  setHidden: (value: boolean) => void
  isRevealed: (key: string) => boolean
  reveal: (key: string) => void
}

const PrivacyContext = createContext<PrivacyValue | null>(null)

export function PrivacyProvider({ children }: { children: ReactNode }) {
  const [hidden, setHidden] = useState(false)
  const [revealed, setRevealed] = useState<ReadonlySet<string>>(() => new Set())
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  useEffect(() => () => {
    for (const timer of timers.current.values()) clearTimeout(timer)
    timers.current.clear()
  }, [])

  const reveal = useCallback((key: string) => {
    const existing = timers.current.get(key)
    if (existing) clearTimeout(existing)
    setRevealed((current) => new Set(current).add(key))
    timers.current.set(key, setTimeout(() => {
      timers.current.delete(key)
      setRevealed((current) => {
        const next = new Set(current)
        next.delete(key)
        return next
      })
    }, 3000))
  }, [])

  const isRevealed = useCallback((key: string) => revealed.has(key), [revealed])
  const value = useMemo(() => ({ hidden, toggle: () => setHidden((current) => !current), setHidden, isRevealed, reveal }), [hidden, isRevealed, reveal])

  return <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>
}

export function usePrivacy(): PrivacyValue {
  const value = useContext(PrivacyContext)
  if (!value) throw new Error('usePrivacy must be used inside PrivacyProvider')
  return value
}
