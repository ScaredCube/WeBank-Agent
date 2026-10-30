import type { ReactNode } from 'react'
import { Eye, EyeOff, Menu } from 'lucide-react'

/** Shared layout only: data and commands belong to the entry point. */
export function BankWorkspace({ sidebar, panel, overlay, children }: {
  sidebar: ReactNode
  panel?: ReactNode
  overlay?: ReactNode
  children: ReactNode
}) {
  return <div className="relative flex h-dvh overflow-hidden bg-panel text-ink">
    {sidebar}
    {panel}
    {overlay}
    <main className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
  </div>
}

export function WorkspaceHeader({ title, isHome = false, sidebarOpen, onOpenSidebar, hidden, onTogglePrivacy, status }: {
  title: string
  isHome?: boolean
  sidebarOpen: boolean
  onOpenSidebar: () => void
  hidden: boolean
  onTogglePrivacy: () => void
  status?: ReactNode
}) {
  return <header className="flex h-16 shrink-0 items-center gap-1 border-b border-line bg-white px-3 sm:gap-3 md:px-6">
    <button id="open-sidebar-button" type="button" onClick={onOpenSidebar} aria-expanded={sidebarOpen} aria-controls="conversation-sidebar" aria-label="打开导航和会话列表" className="grid h-11 w-10 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 xl:hidden">
      <Menu className="size-[18px]" />
    </button>
    <h1 className="min-w-0 flex-1 truncate text-[14px] font-semibold tracking-tight text-ink sm:text-[15px]">
      <span className={isHome ? 'xl:sr-only' : ''}>{title}</span>
    </h1>
    <button type="button" onClick={onTogglePrivacy} className="flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg px-2 text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700" aria-label={hidden ? '显示金额' : '隐藏金额'} aria-pressed={hidden}>
      {hidden ? <EyeOff size={18} /> : <Eye size={18} />}
      <span className="hidden text-xs 2xl:inline">{hidden ? '显示金额' : '隐私模式'}</span>
    </button>
    {status}
  </header>
}
