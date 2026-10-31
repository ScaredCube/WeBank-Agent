import { createContext, useContext } from 'react'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'
export interface ThemeContextValue {
  mode: ThemeMode
  resolved: ResolvedTheme
  setMode: (mode: ThemeMode) => void
  toggle: () => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
const fallback: ThemeContextValue = {
  mode: 'light', resolved: 'light', setMode: () => {}, toggle: () => {},
}

/** Safe light default lets legacy component tests mount outside the whole app. */
export function useTheme() {
  return useContext(ThemeContext) ?? fallback
}
