import { useEffect, useRef, type ReactNode } from 'react'
import { ArrowLeft, Eye, EyeOff, RefreshCw, X } from 'lucide-react'
import type { WorkspacePanelName } from '@/app/workspace-state'

const names: Record<WorkspacePanelName, string> = { assets: '资产', activity: '操作记录', collections: '收藏' }

export function WorkspacePanelFrame({ panel, onClose, hidden, onTogglePrivacy, onRefresh, focusOnMount = true, children }: {
  panel: WorkspacePanelName
  onClose: () => void
  hidden: boolean
  onTogglePrivacy: () => void
  onRefresh?: () => void
  focusOnMount?: boolean
  children: ReactNode
}) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  useEffect(() => {
    if (!focusOnMount) return
    if (!returnFocus.current && document.activeElement instanceof HTMLElement && document.activeElement !== document.body) {
      const sidebar = document.getElementById('conversation-sidebar')
      const fromSidebar = sidebar?.contains(document.activeElement) ?? false
      const mobile = typeof window.matchMedia === 'function' && window.matchMedia('(max-width: 1023px)').matches
      returnFocus.current = fromSidebar && mobile ? document.getElementById('open-sidebar-button') : document.activeElement
    }
    if (returnFocus.current) closeRef.current?.focus()
  }, [focusOnMount])
  function closePanel() {
    const persistentSidebar = typeof window.matchMedia === 'function' && window.matchMedia('(min-width: 1024px)').matches
    const target = persistentSidebar
      ? (returnFocus.current?.isConnected ? returnFocus.current
        : document.querySelector<HTMLButtonElement>(`#conversation-sidebar [data-workspace-panel="${panel}"]`))
      : document.getElementById('open-sidebar-button')
    if (persistentSidebar && target?.isConnected) target.focus()
    onClose()
    // Mobile overlays keep main inert until unmount; restore focus on the next frame.
    if (!persistentSidebar) queueMicrotask(() => { if (target?.isConnected) target.focus() })
  }
  return <section id="workspace-panel" onKeyDown={(event) => { if (event.key === 'Escape' && !event.defaultPrevented) { event.stopPropagation(); closePanel() } }} data-workspace-panel-surface={panel} className="absolute inset-0 z-30 flex flex-col bg-workspace text-ink lg:left-[var(--nav-visible-width)] lg:right-0 lg:border-l lg:border-line lg:shadow-[0_20px_60px_-40px_rgba(0,30,24,.5)] xl:relative xl:inset-auto xl:w-[var(--workspace-panel-width)] xl:shrink-0 xl:rounded-none xl:border-l-0 xl:border-r xl:shadow-none" aria-label={names[panel]}>
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5 sm:px-7">
      <button ref={closeRef} type="button" onClick={closePanel} className="grid size-10 place-items-center rounded-lg text-muted transition hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700" aria-label={panel === 'assets' ? '收起资产区' : '返回对话'}>
        <ArrowLeft size={18} className="lg:hidden" />
        <X size={18} className="hidden lg:block" />
      </button>
      <h2 className="flex-1 text-base font-semibold tracking-tight text-ink">{names[panel]}</h2>
      {panel === 'assets' && <button type="button" onClick={onTogglePrivacy} aria-pressed={hidden} className="flex min-h-10 items-center gap-1.5 rounded-lg px-2 text-[11px] text-muted transition hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700" aria-label={hidden ? '显示金额' : '隐藏金额'}>
        {hidden ? <EyeOff size={15} /> : <Eye size={15} />}{hidden ? '显示金额' : '隐藏金额'}
      </button>}
      {onRefresh && <button type="button" onClick={onRefresh} className="grid size-10 place-items-center rounded-lg text-muted transition hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700" aria-label="刷新"><RefreshCw size={17} /></button>}
    </header>
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-5 pb-9 pt-6 sm:px-7">{children}</div>
  </section>
}
