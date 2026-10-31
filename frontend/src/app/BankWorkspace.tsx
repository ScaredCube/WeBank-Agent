import {
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { GripVertical, Menu } from 'lucide-react'

const DEFAULT_SIDEBAR_WIDTH = 296
const MIN_SIDEBAR_WIDTH = 240
const MAX_SIDEBAR_WIDTH = 400

interface ResizeStart {
  pointerId: number
  x: number
  width: number
}

/** Shared layout only: data and commands belong to the entry point. */
export function BankWorkspace({ sidebar, panel, overlay, children, sidebarCollapsed = false }: {
  sidebar: ReactNode
  panel?: ReactNode
  overlay?: ReactNode
  children: ReactNode
  sidebarCollapsed?: boolean
}) {
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH)
  const [isResizingSidebar, setIsResizingSidebar] = useState(false)
  const resizeStart = useRef<ResizeStart | null>(null)
  const style = {
    '--sidebar-width': `${sidebarWidth}px`,
    '--sidebar-width-transition-duration': isResizingSidebar ? '0ms' : '200ms',
  } as CSSProperties

  function clampSidebarWidth(width: number) {
    return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, width))
  }

  function startResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    resizeStart.current = { pointerId: event.pointerId, x: event.clientX, width: sidebarWidth }
    event.currentTarget.setPointerCapture(event.pointerId)
    setIsResizingSidebar(true)
    event.preventDefault()
  }

  function resize(event: ReactPointerEvent<HTMLDivElement>) {
    const start = resizeStart.current
    if (!start || start.pointerId !== event.pointerId) return
    setSidebarWidth(clampSidebarWidth(start.width + event.clientX - start.x))
  }

  function stopResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (resizeStart.current?.pointerId === event.pointerId) {
      resizeStart.current = null
      setIsResizingSidebar(false)
    }
  }

  function resizeWithKeyboard(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Home') setSidebarWidth(MIN_SIDEBAR_WIDTH)
    else if (event.key === 'End') setSidebarWidth(MAX_SIDEBAR_WIDTH)
    else if (event.key === 'ArrowLeft') setSidebarWidth((width) => clampSidebarWidth(width - 16))
    else if (event.key === 'ArrowRight') setSidebarWidth((width) => clampSidebarWidth(width + 16))
    else return
    event.preventDefault()
  }

  return <div style={style} className="relative flex h-dvh overflow-hidden bg-panel text-ink">
    {sidebar}
    {!sidebarCollapsed && <div
      role="separator"
      aria-orientation="vertical"
      aria-label="调整导航栏宽度"
      aria-controls="conversation-sidebar"
      aria-valuemin={MIN_SIDEBAR_WIDTH}
      aria-valuemax={MAX_SIDEBAR_WIDTH}
      aria-valuenow={sidebarWidth}
      aria-valuetext={`${sidebarWidth} 像素`}
      tabIndex={0}
      onPointerDown={startResize}
      onPointerMove={resize}
      onPointerUp={stopResize}
      onPointerCancel={stopResize}
      onLostPointerCapture={() => { resizeStart.current = null; setIsResizingSidebar(false) }}
      onKeyDown={resizeWithKeyboard}
      onDoubleClick={() => setSidebarWidth(DEFAULT_SIDEBAR_WIDTH)}
      style={{ touchAction: 'none' }}
      className="group hidden w-3 shrink-0 cursor-col-resize select-none items-center justify-center bg-transparent outline-none hover:bg-jade-50/70 focus-visible:bg-jade-50 lg:flex"
    >
      <GripVertical aria-hidden="true" className="size-3.5 text-muted/50 transition-colors group-hover:text-jade-700 group-focus-visible:text-jade-700" strokeWidth={2} />
    </div>}
    {panel}
    {overlay}
    <main className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
  </div>
}

export function WorkspaceHeader({ title, isHome = false, sidebarOpen, onOpenSidebar, status }: {
  title: string
  isHome?: boolean
  sidebarOpen: boolean
  onOpenSidebar: () => void
  status?: ReactNode
}) {
  return <header className="flex h-16 shrink-0 items-center gap-1 border-b border-line bg-white px-3 sm:gap-3 md:px-6">
    <button id="open-sidebar-button" type="button" onClick={onOpenSidebar} aria-expanded={sidebarOpen} aria-controls="conversation-sidebar" aria-label="打开导航和会话列表" title="打开导航和会话列表" className="grid h-11 w-10 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 lg:hidden">
      <Menu className="size-[18px]" />
    </button>
    <h1 className="min-w-0 flex-1 truncate text-[14px] font-semibold tracking-tight text-ink sm:text-[15px]">
      <span className={isHome ? 'lg:sr-only' : ''}>{title}</span>
    </h1>
    {status}
  </header>
}
