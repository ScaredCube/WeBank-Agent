import { LogOut, Plus, X } from 'lucide-react'

import { BrandMark } from '@/components/BrandMark'
import type { Conversation, User } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeId: number | null
  user: User | null
  open: boolean
  disabled?: boolean
  onSelect: (id: number) => void
  onNew: () => void
  onClose: () => void
  onLogout: () => void
}

export function ConversationSidebar({
  conversations,
  activeId,
  user,
  open,
  disabled = false,
  onSelect,
  onNew,
  onClose,
  onLogout,
}: ConversationSidebarProps) {
  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-30 bg-ink/20 backdrop-blur-[2px] md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-[276px] flex-col border-r border-line bg-[#f2f1ec] transition-transform duration-200 ease-out md:static md:z-auto md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center gap-2.5 px-5">
          <BrandMark className="size-8 rounded-[9px]" />
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13.5px] font-semibold tracking-wide text-ink">
              微众银行AI智能体
            </div>
            <div className="text-[9.5px] uppercase tracking-[0.22em] text-muted/60">
              WeBank AI Agent
            </div>
          </div>
          <button
            className="grid size-8 place-items-center rounded-lg text-muted hover:bg-ink/5 md:hidden"
            onClick={onClose}
          >
            <X className="size-4" />
            <span className="sr-only">收起侧栏</span>
          </button>
        </div>

        <div className="px-3">
          <button
            onClick={onNew}
            disabled={disabled}
            className="flex h-10 w-full items-center gap-2 rounded-xl border border-line bg-white/75 px-3 text-[13px] font-medium text-ink shadow-[0_1px_2px_rgba(20,26,22,0.04)] transition hover:bg-white disabled:opacity-50"
          >
            <Plus className="size-4 text-jade-700" />
            新对话
          </button>
        </div>

        <nav className="scroll-thin mt-4 flex-1 overflow-y-auto px-3 pb-4">
          {conversations.length === 0 && (
            <p className="px-3 pt-2 text-[12.5px] text-muted/55">还没有对话</p>
          )}
          <div className="flex flex-col gap-0.5">
            {conversations.map((conversation) => {
              const active = conversation.id === activeId
              return (
                <button
                  key={conversation.id}
                  onClick={() => onSelect(conversation.id)}
                  disabled={disabled}
                  className={cn(
                    'flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left transition disabled:opacity-60',
                    active
                      ? 'bg-white shadow-[0_1px_2px_rgba(20,26,22,0.06)]'
                      : 'hover:bg-white/60',
                  )}
                >
                  <span
                    className={cn(
                      'w-full truncate text-[13px]',
                      active ? 'font-medium text-ink' : 'text-ink/75',
                    )}
                  >
                    {conversation.title}
                  </span>
                  <span className="text-[10.5px] text-muted/50">
                    {formatRelativeTime(conversation.updated_at)}
                  </span>
                </button>
              )
            })}
          </div>
        </nav>

        <div className="border-t border-line/80 p-3">
          <div className="flex items-center gap-2.5 rounded-xl px-2 py-1.5">
            <div className="grid size-8 place-items-center rounded-full bg-jade-100 text-[12px] font-medium text-jade-800">
              {(user?.display_name || '用户').slice(0, 1)}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[12.5px] font-medium text-ink">
                {user?.display_name || '用户'}
              </div>
              <div className="truncate text-[10.5px] text-muted/60">@{user?.username}</div>
            </div>
            <button
              onClick={onLogout}
              title="退出登录"
              className="grid size-8 place-items-center rounded-lg text-muted/60 transition hover:bg-ink/5 hover:text-ink"
            >
              <LogOut className="size-[15px]" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
