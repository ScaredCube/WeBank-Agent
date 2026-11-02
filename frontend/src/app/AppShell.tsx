import { Landmark, Menu, Plus, Sparkles } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef, type ReactNode } from 'react'

import { MASCOT_NAME } from '@/features/theme/brand'
import { DURATION, EASE_DRAWER, EASE_IN_OUT, EASE_OUT, useMotionReduced } from '@/lib/motion'
import { cn } from '@/lib/utils'

/**
 * Three surfaces: assets on the left, conversation in the middle, and the
 * utility drawer (conversations, collections, activity) on the right.
 *
 * Assets stay mounted by the page so dragging and card selection keep state.
 * The utility drawer only mounts while open so its focus trap stays simple.
 */
export function AppShell({ assets, utility, workspace, utilityOpen, onCloseUtility, children }: {
  assets: ReactNode
  utility: ReactNode
  workspace?: ReactNode
  utilityOpen: boolean
  onCloseUtility: () => void
  children: ReactNode
}) {
  const drawerRef = useRef<HTMLDivElement>(null)
  const restoreFocus = useRef<HTMLElement | null>(null)
  const closeUtilityRef = useRef(onCloseUtility)
  const reduced = useMotionReduced()

  useEffect(() => { closeUtilityRef.current = onCloseUtility }, [onCloseUtility])

  useEffect(() => {
    if (!utilityOpen) return
    restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const frame = requestAnimationFrame(() => {
      drawerRef.current?.querySelector<HTMLElement>('[data-utility-close]')?.focus()
    })
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') closeUtilityRef.current()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKeyDown)
      const target = restoreFocus.current
      restoreFocus.current = null
      queueMicrotask(() => { if (target?.isConnected) target.focus() })
    }
  }, [utilityOpen])

  return <div className="bank-app relative flex h-dvh overflow-hidden bg-canvas text-ink">
    {assets}
    <main className="flex min-w-0 flex-1 flex-col bg-panel">{children}</main>
    {workspace}
    <AnimatePresence>
      {utilityOpen && <motion.div key="utility-overlay"
        className="fixed inset-0 z-30 bg-ink/20 backdrop-blur-[2px]"
        onClick={onCloseUtility} aria-hidden="true"
        initial={reduced ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={reduced ? { duration: 0 } : { duration: DURATION.base, ease: EASE_OUT }} />}
      {utilityOpen && <motion.div key="utility-panel" ref={drawerRef}
        className="fixed inset-y-0 right-0 z-40 flex w-[min(372px,88vw)] flex-col border-l border-line bg-sidebar shadow-2xl"
        initial={reduced ? false : { x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%', transition: reduced ? { duration: 0 } : { duration: DURATION.base, ease: EASE_IN_OUT } }}
        transition={reduced ? { duration: 0 } : { duration: DURATION.drawer, ease: EASE_DRAWER }}>
        {utility}
      </motion.div>}
    </AnimatePresence>
  </div>
}

export function AppHeader({ title, isHome, assetsOpen, onToggleAssets, onNewConversation, newConversationDisabled = false, utilityOpen, onOpenUtility }: {
  title: string
  isHome: boolean
  assetsOpen: boolean
  onToggleAssets: () => void
  onNewConversation: () => void
  newConversationDisabled?: boolean
  utilityOpen: boolean
  onOpenUtility: () => void
}) {
  return <header className="relative z-10 flex h-[calc(4rem+env(safe-area-inset-top))] shrink-0 items-center gap-1.5 border-b border-line/70 bg-panel/90 px-3 pt-[env(safe-area-inset-top)] backdrop-blur sm:gap-3 sm:px-5">
    <button type="button" onClick={onToggleAssets} aria-expanded={assetsOpen}
      aria-label={assetsOpen ? '收起资产' : '打开资产'} title={assetsOpen ? '收起资产' : '打开资产'}
      className={cn('flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl px-2.5 text-[12px] font-medium focus-visible:outline-2 focus-visible:outline-jade-700',
        assetsOpen ? 'bg-jade-100 text-jade-900' : 'text-jade-800 hover:bg-jade-50')}>
      <Landmark className="size-[16px]" strokeWidth={1.8} />
      <span>资产</span>
    </button>
    <div className="flex min-w-0 flex-1 items-center justify-center gap-2 px-1">
      <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-lg bg-jade-50 text-jade-800"><Sparkles size={14} /></span>
      <h1 className={cn('min-w-0 truncate text-[13px] font-semibold tracking-tight text-ink/80 sm:text-[14px]', isHome && 'sm:text-[15px]')}>
        {isHome ? MASCOT_NAME : title}
      </h1>
    </div>
    <button type="button" onClick={onNewConversation} disabled={newConversationDisabled}
      title="新建对话" aria-label="新建对话"
      className="grid size-10 shrink-0 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 disabled:opacity-40">
      <Plus size={19} />
    </button>
    <button type="button" onClick={onOpenUtility} aria-expanded={utilityOpen}
      aria-label="打开导航和会话列表" title="打开导航和会话列表"
      className="grid size-10 shrink-0 place-items-center rounded-xl text-muted hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
      <Menu className="size-[18px]" />
    </button>
  </header>
}
