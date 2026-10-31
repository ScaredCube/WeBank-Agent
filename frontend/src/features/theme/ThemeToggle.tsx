import { Moon, Sun } from 'lucide-react'
import { PenguinArt } from './PenguinArt'
import { useTheme } from './theme-context'

/** A theme toggle whose artwork is the current theme's mascot identity. */
export function ThemeToggle({ compact: _compact = false }: { compact?: boolean }) {
  const { resolved, toggle } = useTheme()
  const target = resolved === 'dark' ? '浅色' : '深色'

  return <button
    type="button"
    onClick={toggle}
    aria-label={`切换至${target}主题`}
    title={`切换至${target}主题`}
    aria-pressed={resolved === 'dark'}
    className="relative inline-flex h-11 w-[52px] shrink-0 items-center justify-center rounded-xl border border-transparent transition-colors hover:border-line hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700"
  >
    <PenguinArt pose="avatar" className="size-[32px]" />
    <span aria-hidden="true" className="absolute bottom-[4px] right-[3px] grid size-[18px] place-items-center rounded-full border border-line bg-panel text-muted">
      {resolved === 'dark' ? <Sun size={11} strokeWidth={2.3}/> : <Moon size={11} strokeWidth={2.3}/>}
    </span>
  </button>
}
