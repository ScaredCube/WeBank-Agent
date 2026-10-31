import { Bookmark, CreditCard, History, LogOut, MessageSquareText, PanelLeftClose, Plus, X } from 'lucide-react'
import { useEffect, useRef } from 'react'

import type { WorkspacePanelName } from '@/app/workspace-state'
import { BrandMark } from '@/components/BrandMark'
import { PenguinArt } from '@/features/theme/PenguinArt'
import { MASCOT_NAME } from '@/features/theme/brand'
import type { Conversation, User } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeId: number | null
  user: User | null
  open: boolean
  desktopCollapsed?: boolean
  activePanel: WorkspacePanelName | null
  hideActiveConversation?: boolean
  disabled?: boolean
  newDisabled?: boolean
  disabledReason?: string
  onSelect: (id: number) => void
  onNew: () => void
  onOpenPanel: (panel: WorkspacePanelName | null) => void
  onToggleDesktopSidebar: () => void
  onClose: () => void
  onLogout: () => void
}

export function ConversationSidebar({
  conversations,
  activeId,
  user,
  open,
  desktopCollapsed = false,
  activePanel,
  hideActiveConversation = false,
  disabled = false,
  newDisabled = false,
  disabledReason,
  onSelect,
  onNew,
  onOpenPanel,
  onToggleDesktopSidebar,
  onClose,
  onLogout,
}: ConversationSidebarProps) {
  const closeRef = useRef<HTMLButtonElement>(null)
  const visibleConversations = hideActiveConversation
    ? conversations.filter((conversation) => conversation.id !== activeId)
    : conversations
  const navigation = [
    { id: null, label: '对话', icon: MessageSquareText },
    { id: 'assets' as const, label: '资产', icon: CreditCard },
    { id: 'collections' as const, label: '收藏', icon: Bookmark },
    { id: 'activity' as const, label: '操作记录', icon: History },
  ]
  useEffect(() => {
    if (!open) return
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    closeRef.current?.focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [open])

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-ink/20 backdrop-blur-[2px] lg:hidden"
          onClick={onClose}
        />
      )}
      <aside
        id="conversation-sidebar"
        onKeyDown={(event) => { if (open && event.key === 'Escape') { event.stopPropagation(); onClose() } }}
        aria-label="导航栏"
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[296px] shrink-0 flex-col border-r border-line bg-sidebar lg:static lg:z-auto lg:overflow-hidden lg:transition-[width]',
          open ? 'flex' : 'hidden lg:flex',
          desktopCollapsed ? 'lg:w-[68px]' : 'lg:w-[var(--sidebar-width)]',
        )}
        style={{ transitionDuration: 'var(--sidebar-width-transition-duration, 200ms)' }}
      >
        <div className={cn('flex h-16 shrink-0 items-center gap-3 border-b border-line/65 px-5', desktopCollapsed && 'lg:justify-center lg:px-0')}>
          {desktopCollapsed ? <>
            <BrandMark className="size-9 shrink-0 rounded-[11px] lg:hidden" />
            <button
              type="button"
              aria-label="展开侧栏"
              title="展开侧栏"
              onClick={onToggleDesktopSidebar}
              className="hidden size-9 shrink-0 place-items-center rounded-[10px] transition hover:bg-[#f1f6f4] focus-visible:outline-2 focus-visible:outline-jade-700 lg:grid"
            >
              <BrandMark className="size-9 rounded-[10px]" />
            </button>
          </> : <PenguinArt pose="avatar" className="size-9 shrink-0" />}
          <div className={cn('min-w-0 flex-1 truncate text-[14px] font-bold tracking-[-0.025em] text-ink', desktopCollapsed && 'lg:hidden')}>
            {MASCOT_NAME}
          </div>
          {!desktopCollapsed && <button
            type="button"
            aria-label="折叠导航栏"
            title="收起侧栏"
            onClick={onToggleDesktopSidebar}
            className="hidden size-9 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700 lg:grid"
          >
            <PanelLeftClose className="size-[18px]" />
          </button>}
          <button
            ref={closeRef}
            type="button"
            aria-label="收起侧栏"
            title="收起侧栏"
            className="grid size-9 shrink-0 place-items-center rounded-lg text-muted transition hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-jade-700 lg:hidden"
            onClick={onClose}
          >
            <X className="size-4" />
          </button>
        </div>

        <div className={cn('px-4 pt-5', desktopCollapsed && 'lg:px-0')}>
          <button
            type="button"
            aria-label="新对话"
            title="新对话"
            onClick={onNew}
            disabled={disabled || newDisabled}
            className={cn('flex h-11 w-full items-center gap-2.5 rounded-[11px] bg-jade-100 px-3.5 text-[13px] font-semibold text-jade-900 transition-colors hover:bg-jade-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 disabled:opacity-50', desktopCollapsed && 'lg:mx-auto lg:w-10 lg:justify-center lg:px-0')}
          >
            <Plus className="size-[18px] shrink-0" />
            <span className={desktopCollapsed ? 'lg:hidden' : undefined}>新对话</span>
          </button>
        </div>

        <nav aria-label="主导航" className={cn('mt-8 shrink-0 px-4', desktopCollapsed && 'lg:px-2')}>
          <div className="flex flex-col gap-1">
            {navigation.map(({ id, label, icon: Icon }) => {
              const active = id === activePanel
              return (
                <button
                  key={label}
                  type="button"
                  aria-current={active ? 'page' : undefined}
                  aria-label={label}
                  title={desktopCollapsed ? label : undefined}
                  data-workspace-panel={id ?? 'chat'}
                  onClick={() => onOpenPanel(id)}
                  className={cn(
                    'flex h-11 w-full items-center gap-3 rounded-[11px] px-3 text-left text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-jade-700',
                    desktopCollapsed && 'lg:justify-center lg:px-0',
                    active ? 'bg-jade-100 font-semibold text-jade-900' : 'text-ink/75 hover:bg-jade-50',
                  )}
                >
                  <Icon className="size-[17px] shrink-0" strokeWidth={1.8} />
                  <span className={desktopCollapsed ? 'lg:hidden' : undefined}>{label}</span>
                </button>
              )
            })}
          </div>
        </nav>

        <nav aria-label="最近对话" className={cn('scroll-thin mt-9 min-h-0 flex-1 overflow-y-auto px-4 pb-4', desktopCollapsed && 'lg:hidden')}>
          <h2 className="mb-3 pl-3 text-[10px] font-semibold tracking-[0.14em] text-muted/85">最近对话</h2>
          {disabledReason && <p role="status" className="pb-3 pl-10 text-xs leading-5 text-muted">{disabledReason}</p>}
          {visibleConversations.length === 0 && (
            <div className="flex items-center gap-2 px-3 pt-2"><PenguinArt pose="peek" className="size-11" /><p className="text-[12px] text-muted">还没有对话</p></div>
          )}
          <div className="flex flex-col">
            {visibleConversations.map((conversation) => {
              const active = conversation.id === activeId
              const updatedLabel = formatRelativeTime(conversation.updated_at)
              return (
                <button
                  key={conversation.id}
                  onClick={() => onSelect(conversation.id)}
                  disabled={disabled}
                  aria-current={active ? 'true' : undefined}
                  aria-label={`${conversation.title}，更新于${updatedLabel}`}
                  title={`${conversation.title} · ${updatedLabel}`}
                  className={cn(
                    'relative flex min-h-[54px] w-full items-start gap-3 rounded-[11px] px-3 py-2.5 text-left transition-colors disabled:opacity-60',
                    active
                      ? 'bg-white text-jade-900 shadow-[0_0_0_1px_rgba(16,80,57,0.06)] before:absolute before:bottom-3 before:left-0 before:top-3 before:w-[3px] before:rounded-full before:bg-jade-700'
                      : 'text-ink/75 hover:bg-white/80',
                  )}
                >
                  <MessageSquareText className={cn('mt-1 size-4 shrink-0', active ? 'text-jade-800' : 'text-muted')} strokeWidth={1.8} />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block truncate text-[12.5px]', active ? 'font-semibold' : 'font-medium')}>{conversation.title}</span>
                    {updatedLabel && <span className="mt-0.5 block text-[10.5px] text-muted">{updatedLabel}</span>}
                  </span>
                </button>
              )
            })}
          </div>
        </nav>

        <div className={cn('shrink-0 border-t border-line/80 px-5 py-4', desktopCollapsed && 'lg:px-0')}>
          <div className={cn('flex items-center gap-3', desktopCollapsed && 'lg:justify-center')}>
            <div title={desktopCollapsed ? user?.display_name || '用户' : undefined} className="grid size-8 shrink-0 place-items-center rounded-xl bg-[#d9ebe5] text-[12px] font-semibold text-jade-800">
              {(user?.display_name || '用户').slice(0, 1)}
            </div>
            <div className={cn('min-w-0 flex-1', desktopCollapsed && 'lg:hidden')}>
              <div className="truncate text-[13px] font-semibold text-ink">
                {user?.display_name || '用户'}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-muted">@{user?.username}</div>
            </div>
            <button
              onClick={onLogout}
              title="退出登录"
              aria-label="退出登录"
              className={cn('grid size-9 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700', desktopCollapsed && 'lg:hidden')}
            >
              <LogOut className="size-[15px]" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
