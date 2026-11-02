import { Check, MessageSquareText, MoreHorizontal, Pencil, Plus, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { Conversation } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const referenceDay = (() => {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
})()

interface ConversationListProps {
  conversations: Conversation[]
  activeId: number | null
  hideActiveConversation?: boolean
  disabled?: boolean
  newDisabled?: boolean
  disabledReason?: string
  onSelect: (id: number) => void
  onRename?: (id: number, title: string) => Promise<void>
  onNew: () => void
}

/** Conversation search, grouping and rename live inside the right drawer. */
export function ConversationList({
  conversations, activeId, hideActiveConversation = false,
  disabled = false, newDisabled = false, disabledReason,
  onSelect, onRename, onNew,
}: ConversationListProps) {
  const [query, setQuery] = useState('')
  const [menuId, setMenuId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [renameError, setRenameError] = useState('')
  const [renaming, setRenaming] = useState(false)

  const visibleConversations = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return conversations
      .filter(item => !(hideActiveConversation && item.id === activeId))
      .filter(item => !needle || item.title.toLocaleLowerCase().includes(needle))
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
  }, [conversations, activeId, hideActiveConversation, query])

  const groups = useMemo(() => {
    const start = referenceDay
    const oneDay = 86400000
    const grouped = new Map<string, Conversation[]>()
    for (const conversation of visibleConversations) {
      const age = start - Date.parse(conversation.updated_at)
      const name = age < oneDay ? '今天' : age < 2 * oneDay ? '昨天' : age < 7 * oneDay ? '近七天' : '更早'
      grouped.set(name, [...(grouped.get(name) ?? []), conversation])
    }
    return [...grouped]
  }, [visibleConversations])

  async function submitRename(id: number) {
    const title = editingTitle.trim()
    if (!title || !onRename || renaming) return
    setRenaming(true); setRenameError('')
    try { await onRename(id, title); setEditingId(null); setMenuId(null) }
    catch (error) { setRenameError(error instanceof Error ? error.message : '重命名失败，请重试') }
    finally { setRenaming(false) }
  }

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="shrink-0 px-4 pt-4">
      <button type="button" aria-label="新对话" onClick={onNew} disabled={disabled || newDisabled}
        className="flex h-11 w-full items-center gap-2.5 rounded-[11px] bg-jade-100 px-3.5 text-[13px] font-semibold text-jade-900 hover:bg-jade-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 disabled:opacity-50">
        <Plus className="size-[18px] shrink-0" />
        <span>新对话</span>
      </button>
      <label className="mt-4 flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-muted focus-within:border-jade-400">
        <Search size={16} aria-hidden="true" />
        <span className="sr-only">搜索会话标题</span>
        <input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索对话"
          className="min-w-0 w-full bg-transparent text-sm text-ink outline-none placeholder:text-muted" />
        {query && <button type="button" aria-label="清空会话搜索" onClick={() => setQuery('')}><X size={15} /></button>}
      </label>
      {disabledReason && <p role="status" className="mt-3 px-1 text-xs leading-5 text-muted">{disabledReason}</p>}
    </div>

    <nav aria-label="最近对话" className="scroll-thin mt-4 min-h-0 flex-1 overflow-y-auto px-4 pb-4">
      {visibleConversations.length === 0 && <p className="px-3 py-5 text-sm text-muted">{query ? '没有匹配的对话' : '还没有对话，试着创建一个。'}</p>}
      <div className="space-y-5">
        {groups.map(([groupName, items]) => <section key={groupName} aria-label={groupName}>
          <h3 className="mb-2 px-3 text-xs font-medium text-muted">{groupName}</h3>
          <div className="space-y-1">
            {items.map(conversation => {
              const active = conversation.id === activeId
              const updatedLabel = formatRelativeTime(conversation.updated_at)
              return <div key={conversation.id} className={cn('group/conversation relative rounded-xl', active ? 'bg-jade-50 text-jade-900' : 'text-ink/80 hover:bg-jade-50/60')}>
                {editingId === conversation.id ? <form onSubmit={event => { event.preventDefault(); void submitRename(conversation.id) }} className="p-2">
                  <label className="sr-only" htmlFor={`rename-${conversation.id}`}>会话名称</label>
                  <input id={`rename-${conversation.id}`} autoFocus maxLength={60} value={editingTitle} onChange={event => setEditingTitle(event.target.value)}
                    onKeyDown={event => { if (event.key === 'Escape') { setEditingId(null); setRenameError('') } }}
                    className="min-h-9 w-full rounded-lg border border-jade-300 bg-panel px-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-jade-700" />
                  <div className="mt-2 flex items-center justify-end gap-2">
                    <button type="button" onClick={() => { setEditingId(null); setRenameError('') }} className="rounded-lg px-2 py-1.5 text-xs text-muted">取消</button>
                    <button type="submit" disabled={!editingTitle.trim() || renaming} className="inline-flex items-center gap-1 rounded-lg bg-jade-700 px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"><Check size={13} />保存</button>
                  </div>
                  {renameError && <p role="alert" className="mt-1 text-xs text-red-700">{renameError}</p>}
                </form> : <div className="flex items-center">
                  <button type="button" disabled={disabled} onClick={() => { setMenuId(null); onSelect(conversation.id) }}
                    aria-current={active ? 'true' : undefined} aria-label={`${conversation.title}，更新于${updatedLabel}`}
                    className={cn('relative flex min-h-[56px] min-w-0 flex-1 items-center gap-2.5 rounded-xl py-2.5 pl-3 text-left focus-visible:outline-2 focus-visible:outline-jade-700 disabled:opacity-50', active && 'before:absolute before:inset-y-3 before:left-0 before:w-[3px] before:rounded-full before:bg-jade-700')}>
                    <MessageSquareText size={17} className="shrink-0 text-muted" strokeWidth={1.8} />
                    <span className="min-w-0 flex-1">
                      <span className={cn('block truncate text-[13px]', active ? 'font-semibold' : 'font-medium')}>{conversation.title}</span>
                      <span className="mt-0.5 block text-[11px] text-muted">{updatedLabel}</span>
                    </span>
                  </button>
                  {onRename && <div className="relative mr-1">
                    <button type="button" title="管理对话" aria-label="管理会话" aria-expanded={menuId === conversation.id}
                      onClick={() => setMenuId(menuId === conversation.id ? null : conversation.id)}
                      className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700"><MoreHorizontal size={17} /></button>
                    {menuId === conversation.id && <div className="absolute right-0 top-10 z-30 min-w-32 rounded-xl border border-line bg-panel p-1 shadow-lg">
                      <button type="button" onClick={() => { setEditingId(conversation.id); setEditingTitle(conversation.title); setRenameError(''); setMenuId(null) }}
                        className="flex min-h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-ink hover:bg-jade-50"><Pencil size={14} />重命名</button>
                    </div>}
                  </div>}
                </div>}
              </div>
            })}
          </div>
        </section>)}
      </div>
    </nav>
  </div>
}
