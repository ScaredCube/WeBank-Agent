import { useState, type ReactNode } from 'react'
import { ChevronDown } from 'lucide-react'

interface AssetEntryProps {
  title: string
  detail: string
  status?: string
  hidden: boolean
  hiddenLabel?: string
  leading?: ReactNode
  children: ReactNode
}

export function AssetEntry({
  title,
  detail,
  status,
  hidden,
  hiddenLabel = '内容已隐藏',
  leading,
  children,
}: AssetEntryProps) {
  const [open, setOpen] = useState(false)
  const headerStateClass = open ? 'bg-jade-50/60' : 'hover:bg-jade-50/50'

  return (
    <article className="overflow-hidden rounded-xl border border-line bg-white">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className={`group flex w-full items-center gap-3 px-4 py-4 text-left transition-colors focus-visible:outline-2 focus-visible:outline-jade-700 ${headerStateClass}`}
      >
        {leading}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink">
            {hidden ? hiddenLabel : title}
          </span>
          <span className="mt-1 block text-xs leading-5 text-muted">
            {hidden ? '••••' : detail}
          </span>
        </span>
        {status && <span className="text-xs text-muted">{status}</span>}
        <ChevronDown
          size={16}
          className={`shrink-0 text-muted transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && <div className="border-t border-line px-4 py-4">{children}</div>}
    </article>
  )
}
