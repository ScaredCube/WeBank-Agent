import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import { GripVertical, Menu } from 'lucide-react'
import { ThemeToggle } from '@/features/theme/ThemeToggle'

const DEFAULT_SIDEBAR_WIDTH = 296
const MIN_SIDEBAR_WIDTH = 240
const MAX_SIDEBAR_WIDTH = 400
const DEFAULT_PANEL_WIDTH = 500
const MIN_PANEL_WIDTH = 360
const MAX_PANEL_WIDTH = 760
const PANEL_STORAGE = 'webank-agent-panel-width'

function initialPanelWidth() {
  try {
    const value = Number(localStorage.getItem(PANEL_STORAGE))
    if (Number.isFinite(value) && value >= MIN_PANEL_WIDTH && value <= MAX_PANEL_WIDTH) return value
  } catch { /* optional persistence */ }
  return DEFAULT_PANEL_WIDTH
}

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
  const [panelWidth, setPanelWidth] = useState(initialPanelWidth)
  const [resizingPanel, setResizingPanel] = useState(false)
  const panelResizeStart = useRef<ResizeStart | null>(null)
  const [isResizingSidebar, setIsResizingSidebar] = useState(false)
  const [overlayMode, setOverlayMode] = useState(() => typeof window !== 'undefined' &&
    (window.matchMedia?.('(max-width: 1279px)').matches ?? false))
  const resizeStart = useRef<ResizeStart | null>(null)

  useEffect(() => {
    const media = window.matchMedia?.('(max-width: 1279px)')
    if (!media) return
    const update = (event: MediaQueryListEvent) => setOverlayMode(event.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  function clampPanelWidth(width: number) {
    const navWidth = sidebarCollapsed ? 68 : sidebarWidth + 12
    const available = typeof window === 'undefined' ? MAX_PANEL_WIDTH : window.innerWidth - navWidth - 440 - 12
    return Math.max(MIN_PANEL_WIDTH, Math.min(MAX_PANEL_WIDTH, available, width))
  }
  useEffect(() => {
    try { localStorage.setItem(PANEL_STORAGE, String(panelWidth)) } catch { /* storage optional */ }
  }, [panelWidth])
  function startPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType === 'mouse' && event.button !== 0) return
    panelResizeStart.current = {pointerId:event.pointerId,x:event.clientX,width:panelWidth}
    event.currentTarget.setPointerCapture(event.pointerId)
    setResizingPanel(true)
    event.preventDefault()
  }
  function movePanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    const start = panelResizeStart.current
    if (!start || start.pointerId !== event.pointerId) return
    setPanelWidth(clampPanelWidth(start.width + event.clientX - start.x))
  }
  function stopPanelResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (panelResizeStart.current?.pointerId !== event.pointerId) return
    panelResizeStart.current = null
    setResizingPanel(false)
  }
  function panelResizeKey(event: ReactKeyboardEvent<HTMLDivElement>) {
    const delta = event.shiftKey ? 48 : 16
    if (event.key === 'ArrowLeft') setPanelWidth(w => clampPanelWidth(w - delta))
    else if (event.key === 'ArrowRight') setPanelWidth(w => clampPanelWidth(w + delta))
    else if (event.key === 'Home') setPanelWidth(MIN_PANEL_WIDTH)
    else if (event.key === 'End') setPanelWidth(clampPanelWidth(MAX_PANEL_WIDTH))
    else return
    event.preventDefault()
  }
  const style = {
    '--sidebar-width': `${sidebarWidth}px`,
    '--sidebar-width-transition-duration': isResizingSidebar ? '0ms' : '200ms',
    '--nav-visible-width': sidebarCollapsed ? '68px' : `${sidebarWidth + 12}px`,
    '--workspace-panel-width': `${Math.min(panelWidth,clampPanelWidth(panelWidth))}px`,
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

  return <div style={style} className="bank-app relative flex h-dvh overflow-hidden bg-canvas text-ink">
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
    {panel && <div
      role="separator"
      aria-orientation="vertical"
      aria-label="调整资源区与对话区宽度"
      aria-controls="workspace-panel"
      aria-valuemin={MIN_PANEL_WIDTH}
      aria-valuemax={clampPanelWidth(MAX_PANEL_WIDTH)}
      aria-valuenow={Math.min(panelWidth,clampPanelWidth(panelWidth))}
      aria-valuetext={`${Math.min(panelWidth,clampPanelWidth(panelWidth))} 像素`}
      tabIndex={0}
      onPointerDown={startPanelResize}
      onPointerMove={movePanelResize}
      onPointerUp={stopPanelResize}
      onPointerCancel={stopPanelResize}
      onLostPointerCapture={() => { panelResizeStart.current = null;setResizingPanel(false) }}
      onKeyDown={panelResizeKey}
      onDoubleClick={() => setPanelWidth(clampPanelWidth(DEFAULT_PANEL_WIDTH))}
      style={{touchAction:'none'}}
      className={'group hidden w-3 shrink-0 cursor-col-resize select-none items-center justify-center hover:bg-jade-50 focus-visible:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700 xl:flex ' + (resizingPanel ? 'bg-jade-50' : '')}
    ><GripVertical aria-hidden="true" size={14} className="text-muted/55 group-hover:text-jade-700"/></div>}
    {overlay}
    <main inert={Boolean(panel && overlayMode)} className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
  </div>
}

export function WorkspaceHeader({ title, isHome = false, sidebarOpen, onOpenSidebar, status }: {
  title: string
  isHome?: boolean
  sidebarOpen: boolean
  onOpenSidebar: () => void
  status?: ReactNode
}) {
  return <header className="flex h-16 shrink-0 items-center gap-1 border-b border-line/70 bg-panel px-5 sm:gap-3 sm:px-7">
    <button id="open-sidebar-button" type="button" onClick={onOpenSidebar} aria-expanded={sidebarOpen} aria-controls="conversation-sidebar" aria-label="打开导航和会话列表" title="打开导航和会话列表" className="grid h-11 w-10 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 lg:hidden">
      <Menu className="size-[18px]" />
    </button>
    <h1 className="min-w-0 flex-1 truncate text-[13px] font-semibold tracking-tight text-ink/80 sm:text-[14px]">
      <span className={isHome ? 'lg:sr-only' : ''}>{isHome ? '微众银行' : title}</span>
    </h1>
    {status}
    <ThemeToggle compact />
  </header>
}
