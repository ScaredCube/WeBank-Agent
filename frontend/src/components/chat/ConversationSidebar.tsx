import { Bookmark, CreditCard, History, LogOut, MessageSquareText, Plus, X } from 'lucide-react'
import { useEffect, useRef } from 'react'

import type { WorkspacePanelName } from '@/app/workspace-state'
import { BrandMark } from '@/components/BrandMark'
import type { Conversation, User } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeId: number | null
  user: User | null
  open: boolean
  activePanel: WorkspacePanelName | null
  hideActiveConversation?: boolean
  disabled?: boolean
  newDisabled?: boolean
  disabledReason?: string
  onSelect: (id: number) => void
  onNew: () => void
  onOpenPanel: (panel: WorkspacePanelName | null) => void
  onClose: () => void
  onLogout: () => void
}

export function ConversationSidebar({
  conversations,
  activeId,
  user,
  open,
  activePanel,
  hideActiveConversation = false,
  disabled = false,
  newDisabled = false,
  disabledReason,
  onSelect,
  onNew,
  onOpenPanel,
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
          className="fixed inset-0 z-30 bg-ink/20 backdrop-blur-[2px] xl:hidden"
          onClick={onClose}
        />
      )}
      <aside
        id="conversation-sidebar"
        onKeyDown={(event) => { if (open && event.key === 'Escape') { event.stopPropagation(); onClose() } }}
        className={cn(
          'fixed inset-y-0 left-0 z-40 w-[296px] flex-col border-r border-line bg-sidebar xl:static xl:z-auto xl:flex',
          open ? 'flex' : 'hidden',
        )}
      >
        <div className="flex h-[76px] items-center gap-3 px-5">
          <BrandMark className="size-10 rounded-[11px]" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[14px] font-semibold tracking-tight text-ink">
              微众银行AI智能体
            </div>
            <div className="mt-1 text-[10px] tracking-[0.12em] text-muted">WEBANK AI AGENT</div>
          </div>
          <button
            ref={closeRef}
            className="grid size-8 place-items-center rounded-lg text-muted hover:bg-ink/5 xl:hidden"
            onClick={onClose}
          >
            <X className="size-4" />
            <span className="sr-only">收起侧栏</span>
          </button>
        </div>

        <div className="px-5 pt-2">
          <button
            onClick={onNew}
            disabled={disabled || newDisabled}
            className="flex h-12 w-full items-center gap-3 rounded-[10px] bg-jade-800 px-4 text-[14px] font-semibold text-white transition-[background-color,transform] hover:bg-jade-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 active:scale-[0.99] disabled:opacity-50"
          >
            <Plus className="size-[18px]" />
            新对话
          </button>
        </div>

        <nav aria-label="主导航" className="mt-4 px-5">
          <div className="flex flex-col gap-0.5">
            {navigation.map(({ id, label, icon: Icon }) => {
              const active = id === activePanel
              return (
                <button
                  key={label}
                  type="button"
                  aria-current={active ? 'page' : undefined}
                  data-workspace-panel={id ?? 'chat'}
                  onClick={() => onOpenPanel(id)}
                  className={cn(
                    'flex h-11 w-full items-center gap-3 rounded-[9px] px-4 text-left text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-jade-700',
                    active ? 'bg-[#eaf3ef] font-semibold text-jade-800' : 'text-ink/80 hover:bg-[#f0f5f2]',
                  )}
                >
                  <Icon className="size-[17px] shrink-0" strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              )
            })}
          </div>
        </nav>

        <nav aria-label="最近对话" className="scroll-thin mt-7 flex-1 overflow-y-auto px-5 pb-4">
          <h2 className="mb-2 px-2 text-[11px] font-medium text-muted">最近对话</h2>
          {disabledReason && <p role="status" className="px-2 pb-3 text-xs leading-5 text-muted">{disabledReason}</p>}
          {visibleConversations.length === 0 && (
            <p className="px-2 pt-2 text-[12.5px] text-muted/70">还没有对话</p>
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
                    'relative flex min-h-[58px] w-full items-start gap-2 border-b border-line/80 px-3 py-3 text-left transition-colors disabled:opacity-60',
                    active
                      ? 'bg-white/70 text-jade-900 before:absolute before:bottom-3 before:left-0 before:top-3 before:w-0.5 before:rounded-full before:bg-jade-700'
                      : 'text-ink/80 hover:bg-white/60',
                  )}
                >
                  <MessageSquareText className={cn('mt-0.5 size-4 shrink-0', active ? 'text-jade-800' : 'text-muted')} strokeWidth={1.8} />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block truncate text-[12.5px]', active ? 'font-semibold' : 'font-medium')}>{conversation.title}</span>
                    {updatedLabel && <span className="mt-1 block text-[10.5px] text-muted">{updatedLabel}</span>}
                  </span>
                </button>
              )
            })}
          </div>
        </nav>

        <div className="border-t border-line/80 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-full bg-[#d9ebe5] text-[13px] font-semibold text-jade-800">
              {(user?.display_name || '用户').slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold text-ink">
                {user?.display_name || '用户'}
              </div>
              <div className="mt-0.5 truncate text-[11px] text-muted">@{user?.username}</div>
            </div>
            <button
              onClick={onLogout}
              title="退出登录"
              aria-label="退出登录"
              className="grid size-9 place-items-center rounded-lg text-muted transition hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700"
            >
              <LogOut className="size-[15px]" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
