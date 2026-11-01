import { Menu, Sparkles } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

import { MASCOT_NAME } from '@/features/theme/brand'
import { usePrivacy } from '@/features/privacy/PrivacyProvider'
import { Eye, EyeOff } from 'lucide-react'
import { cn } from '@/lib/utils'

export function AppShell({ sidebar, panel, onClosePanel, children }: {
  sidebar: ReactNode
  panel: ReactNode | null
  onClosePanel: () => void
  children: ReactNode
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const restoreFocus = useRef<HTMLElement | null>(null)
  const closePanelRef = useRef(onClosePanel)
  const hasPanel = Boolean(panel)
  useEffect(() => { closePanelRef.current = onClosePanel }, [onClosePanel])
  useEffect(() => {
    if (!hasPanel) return
    restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusPanel = () => panelRef.current?.querySelector<HTMLElement>('button')?.focus()
    const frame = requestAnimationFrame(focusPanel)
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') closePanelRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKeyDown)
      const target = restoreFocus.current
      restoreFocus.current = null
      queueMicrotask(() => { if (target?.isConnected) target.focus() })
    }
  }, [hasPanel])

  return <div className="bank-app relative flex h-dvh overflow-hidden bg-canvas text-ink">
    {sidebar}
    <main className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
    {panel && <div ref={panelRef} className="fixed inset-0 z-50 xl:static xl:z-auto xl:flex xl:w-[min(430px,38vw)] xl:shrink-0 xl:border-l xl:border-line">
      <div className="h-full w-full animate-[slide-in_.32s_cubic-bezier(.32,.72,0,1)] bg-workspace shadow-2xl xl:shadow-none">{panel}</div>
    </div>}
  </div>
}

export function AppHeader({ title, isHome, sidebarOpen, onOpenSidebar, panelOpen, onOpenPanel, onClosePanel }: {
  title: string
  isHome: boolean
  sidebarOpen: boolean
  onOpenSidebar: () => void
  panelOpen: boolean
  onOpenPanel: () => void
  onClosePanel: () => void
}) {
  const privacy = usePrivacy()
  return <header className="relative z-10 flex h-16 shrink-0 items-center gap-1.5 border-b border-line/70 bg-panel/90 px-3 backdrop-blur sm:gap-3 sm:px-5">
    <button type="button" onClick={onOpenSidebar} aria-expanded={sidebarOpen}
      aria-label="打开导航和会话列表" title="打开导航和会话列表"
      className="grid size-10 shrink-0 place-items-center rounded-xl text-muted transition hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
      <Menu className="size-[18px]" />
    </button>
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-lg bg-jade-50 text-jade-800"><Sparkles size={14} /></span>
      <h1 className={cn('min-w-0 truncate text-[13px] font-semibold tracking-tight text-ink/80 sm:text-[14px]', isHome && 'sm:text-[15px]')}>
        {isHome ? MASCOT_NAME : title}
      </h1>
    </div>
    <button type="button" onClick={privacy.toggle} aria-pressed={privacy.hidden}
      title={privacy.hidden ? '显示金额' : '隐藏金额'}
      aria-label={privacy.hidden ? '显示金额' : '隐藏金额'}
      className="grid size-10 place-items-center rounded-xl text-muted transition hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
      {privacy.hidden ? <EyeOff size={17} /> : <Eye size={17} />}
    </button>
    <button type="button" id="open-assets-button" onClick={panelOpen ? onClosePanel : onOpenPanel}
      aria-expanded={panelOpen} aria-label={panelOpen ? '收起资产' : '打开资产'}
      className={cn('flex min-h-10 items-center gap-1.5 rounded-xl px-3 text-[12px] font-medium transition focus-visible:outline-2 focus-visible:outline-jade-700',
        panelOpen ? 'bg-jade-100 text-jade-900' : 'text-jade-800 hover:bg-jade-50')}>
      资产
    </button>
  </header>
}
