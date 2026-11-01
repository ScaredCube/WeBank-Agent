import { Bookmark, Check, CreditCard, History, LogOut, MessageSquareText, MoreHorizontal, PanelLeftClose, Pencil, Plus, Search, X } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { WorkspacePanelName } from '@/app/workspace-state'
import { PenguinArt } from '@/features/theme/PenguinArt'
import { MASCOT_NAME } from '@/features/theme/brand'
import type { Conversation, User } from '@/lib/api'
import { formatRelativeTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const sidebarReferenceDay = (() => {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
})()

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
  onRename?: (id: number, title: string) => Promise<void>
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
  onRename,
  onNew,
  onOpenPanel,
  onToggleDesktopSidebar,
  onClose,
  onLogout,
}: ConversationSidebarProps) {
  const closeRef = useRef<HTMLButtonElement>(null)
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
    const start = sidebarReferenceDay
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
            <PenguinArt pose="avatar" className="size-9 shrink-0 lg:hidden" />
            <button
              type="button"
              aria-label="展开侧栏"
              title="展开侧栏"
              onClick={onToggleDesktopSidebar}
              className="hidden size-9 shrink-0 place-items-center rounded-[10px] transition hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700 lg:grid"
            >
              <PenguinArt pose="avatar" className="size-9" />
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

        <nav aria-label="最近对话" className={cn('scroll-thin mt-7 min-h-0 flex-1 overflow-y-auto px-4 pb-4', desktopCollapsed && 'lg:hidden')}>
          <div className="mb-3 flex items-center justify-between gap-2 px-2">
            <h2 className="text-xs font-semibold tracking-wide text-muted">最近对话</h2>
            <button type="button" onClick={onNew} disabled={disabled || newDisabled} aria-label="从历史列表新建对话" title="新对话" className="grid size-9 place-items-center rounded-xl text-jade-800 transition hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700 disabled:opacity-40"><Plus size={18}/></button>
          </div>
          <label className="mb-4 flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-muted focus-within:border-jade-400">
            <Search size={16} aria-hidden="true"/>
            <span className="sr-only">搜索会话标题</span>
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索对话" className="min-w-0 w-full bg-transparent text-sm text-ink outline-none placeholder:text-muted"/>
            {query && <button type="button" aria-label="清空会话搜索" onClick={() => setQuery('')}><X size={15}/></button>}
          </label>
          {disabledReason && <p role="status" className="mb-3 px-2 text-xs leading-5 text-muted">{disabledReason}</p>}
          {visibleConversations.length === 0 && <p className="px-3 py-5 text-sm text-muted">{query ? '没有匹配的对话' : '还没有对话，试着创建一个。'}</p>}
          <div className="space-y-5">
            {groups.map(([groupName, items]) => <section key={groupName} aria-label={groupName}>
              <h3 className="mb-2 px-3 text-xs font-medium text-muted">{groupName}</h3>
              <div className="space-y-1">
                {items.map(conversation => {
                  const active = conversation.id === activeId
                  const updatedLabel = formatRelativeTime(conversation.updated_at)
                  return <div key={conversation.id} className={cn('group/conversation relative rounded-xl transition-colors',active ? 'bg-jade-50 text-jade-900' : 'text-ink/80 hover:bg-jade-50/60')}>
                    {editingId === conversation.id ? <form onSubmit={event => { event.preventDefault(); void submitRename(conversation.id) }} className="p-2">
                      <label className="sr-only" htmlFor={`rename-${conversation.id}`}>会话名称</label>
                      <input id={`rename-${conversation.id}`} autoFocus maxLength={60} value={editingTitle} onChange={event=>setEditingTitle(event.target.value)}
                        onKeyDown={event=>{if(event.key==='Escape'){setEditingId(null);setRenameError('')}}}
                        className="min-h-9 w-full rounded-lg border border-jade-300 bg-panel px-2 text-sm text-ink focus-visible:outline-2 focus-visible:outline-jade-700"/>
                      <div className="mt-2 flex items-center justify-end gap-2">
                        <button type="button" onClick={()=>{setEditingId(null);setRenameError('')}} className="rounded-lg px-2 py-1.5 text-xs text-muted">取消</button>
                        <button type="submit" disabled={!editingTitle.trim() || renaming} className="inline-flex items-center gap-1 rounded-lg bg-jade-700 px-2.5 py-1.5 text-xs font-semibold text-white disabled:opacity-50"><Check size={13}/>保存</button>
                      </div>
                      {renameError && <p role="alert" className="mt-1 text-xs text-red-700">{renameError}</p>}
                    </form> : <div className="flex items-center">
                      <button type="button" disabled={disabled} onClick={()=>{setMenuId(null);onSelect(conversation.id)}}
                        aria-current={active ? 'true' : undefined} aria-label={`${conversation.title}，更新于${updatedLabel}`}
                        className={cn('relative flex min-h-[56px] min-w-0 flex-1 items-center gap-2.5 rounded-xl py-2.5 pl-3 text-left focus-visible:outline-2 focus-visible:outline-jade-700 disabled:opacity-50',active && 'before:absolute before:inset-y-3 before:left-0 before:w-[3px] before:rounded-full before:bg-jade-700')}>
                        <MessageSquareText size={17} className="shrink-0 text-muted" strokeWidth={1.8}/>
                        <span className="min-w-0 flex-1"><span className={cn('block truncate text-[13px]',active?'font-semibold':'font-medium')}>{conversation.title}</span><span className="mt-0.5 block text-[11px] text-muted">{updatedLabel}</span></span>
                      </button>
                      {onRename && <div className="relative mr-1">
                        <button type="button" title="管理对话" aria-label="管理会话" aria-expanded={menuId===conversation.id}
                          onClick={()=>setMenuId(menuId===conversation.id?null:conversation.id)} className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700"><MoreHorizontal size={17}/></button>
                        {menuId===conversation.id && <div className="absolute right-0 top-10 z-30 min-w-32 rounded-xl border border-line bg-panel p-1 shadow-lg">
                          <button type="button" onClick={()=>{setEditingId(conversation.id);setEditingTitle(conversation.title);setRenameError('');setMenuId(null)}} className="flex min-h-9 w-full items-center gap-2 rounded-lg px-3 text-left text-sm text-ink hover:bg-jade-50"><Pencil size={14}/>重命名</button>
                        </div>}
                      </div>}
                    </div>}
                  </div>
                })}
              </div>
            </section>)}
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
