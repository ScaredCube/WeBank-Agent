import { Bookmark, History, LogOut, MessageSquareText, X } from 'lucide-react'
import type { ReactNode } from 'react'

import type { UtilityTabName } from '@/app/workspace-state'
import { PenguinArt } from '@/features/theme/PenguinArt'
import { MASCOT_NAME } from '@/features/theme/brand'
import type { Conversation, User } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ConversationList } from './ConversationList'

const tabs: { id: UtilityTabName; label: string; icon: typeof MessageSquareText }[] = [
  { id: 'conversations', label: '对话', icon: MessageSquareText },
  { id: 'collections', label: '收藏', icon: Bookmark },
  { id: 'activity', label: '操作记录', icon: History },
]

interface UtilitySidebarProps {
  tab: UtilityTabName
  onTabChange: (tab: UtilityTabName) => void
  conversations: Conversation[]
  activeId: number | null
  user: User | null
  hideActiveConversation?: boolean
  disabled?: boolean
  newDisabled?: boolean
  disabledReason?: string
  collections: ReactNode
  activity: ReactNode
  onSelect: (id: number) => void
  onRename?: (id: number, title: string) => Promise<void>
  onNew: () => void
  onClose: () => void
  onLogout: () => void
}

/** Low-frequency surfaces behind the right-side menu button. */
export function UtilitySidebar({
  tab, onTabChange, conversations, activeId, user, hideActiveConversation,
  disabled, newDisabled, disabledReason, collections, activity,
  onSelect, onRename, onNew, onClose, onLogout,
}: UtilitySidebarProps) {
  return <aside id="utility-sidebar" aria-label="导航栏" className="flex h-full min-h-0 w-full flex-col">
    <header className="flex h-[calc(4rem+env(safe-area-inset-top))] shrink-0 items-center gap-3 border-b border-line/65 px-4 pt-[env(safe-area-inset-top)]">
      <PenguinArt pose="avatar" className="size-9 shrink-0" />
      <div className="min-w-0 flex-1 truncate text-[14px] font-bold tracking-[-0.025em] text-ink">{MASCOT_NAME}</div>
      <button type="button" data-utility-close onClick={onClose} aria-label="收起侧栏" title="收起侧栏"
        className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-ink/5 focus-visible:outline-2 focus-visible:outline-jade-700">
        <X className="size-4" />
      </button>
    </header>

    <nav aria-label="侧栏分区" className="shrink-0 border-b border-line/70 px-3 py-3">
      <div className="grid grid-cols-3 gap-1 rounded-xl bg-jade-50/70 p-1">
        {tabs.map(({ id, label, icon: Icon }) => {
          const active = id === tab
          return <button key={id} type="button" aria-current={active ? 'page' : undefined}
            aria-label={label} onClick={() => onTabChange(id)}
            className={cn('flex min-h-10 items-center justify-center gap-1.5 rounded-lg px-1 text-[12px] focus-visible:outline-2 focus-visible:outline-jade-700',
              active ? 'bg-panel font-semibold text-jade-900 shadow-sm' : 'text-muted hover:text-ink')}>
            <Icon className="size-[15px] shrink-0" strokeWidth={1.8} />
            <span className="truncate">{label}</span>
          </button>
        })}
      </div>
    </nav>

    <div className="flex min-h-0 flex-1 flex-col">
      {tab === 'conversations' && <ConversationList
        conversations={conversations}
        activeId={activeId}
        hideActiveConversation={hideActiveConversation}
        disabled={disabled}
        newDisabled={newDisabled}
        disabledReason={disabledReason}
        onSelect={onSelect}
        onRename={onRename}
        onNew={onNew}
      />}
      {tab === 'collections' && <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 py-4">{collections}</div>}
      {tab === 'activity' && <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-4 py-4">{activity}</div>}
    </div>

    <div className="shrink-0 border-t border-line/80 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4">
      <div className="flex items-center gap-3">
        <div className="grid size-8 shrink-0 place-items-center rounded-xl bg-[#d9ebe5] text-[12px] font-semibold text-jade-800">
          {(user?.display_name || '用户').slice(0, 1)}
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-semibold text-ink">{user?.display_name || '用户'}</div>
          <div className="mt-0.5 truncate text-[11px] text-muted">@{user?.username}</div>
        </div>
        <button type="button" onClick={onLogout} title="退出登录" aria-label="退出登录"
          className="grid size-9 place-items-center rounded-lg text-muted hover:bg-[#f1f6f4] hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
          <LogOut className="size-[15px]" />
        </button>
      </div>
    </div>
  </aside>
}
