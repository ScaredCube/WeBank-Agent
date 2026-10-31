import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ChevronRight } from 'lucide-react'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import { cardSchema, type CardOrigin } from '@/features/intelligent-ui/schema'
import { clearSnapshots, deleteSnapshot, listSnapshots, type Snapshot } from './store'

export function CollectionPanel({ userId, hidden, databaseName, onOpenSource, sourceDisabled = false }: { userId: number; hidden: boolean; databaseName?: string; onOpenSource?: (origin: CardOrigin) => void; sourceDisabled?: boolean }) {
  return <UserCollection key={`${databaseName ?? 'default'}:${userId}`} userId={userId} hidden={hidden} databaseName={databaseName} onOpenSource={onOpenSource} sourceDisabled={sourceDisabled} />
}

function UserCollection({ userId, hidden, databaseName, onOpenSource, sourceDisabled }: { userId: number; hidden: boolean; databaseName?: string; onOpenSource?: (origin: CardOrigin) => void; sourceDisabled: boolean }) {
  const [items, setItems] = useState<Snapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const returnToId = useRef<string | null>(null)
  const focusList = useRef(false)
  const listRef = useRef<HTMLElement>(null)
  const itemButtons = useRef(new Map<string, HTMLButtonElement>())
  const selected = items.find((item) => item.id === selectedId)

  useEffect(() => {
    let active = true
    void listSnapshots(userId, databaseName).then((rows) => { if (active) setItems(rows) }).catch(() => { if (active) setError('无法读取本地收藏。') }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [userId, databaseName])

  useEffect(() => {
    if (selectedId === null && returnToId.current) {
      itemButtons.current.get(returnToId.current)?.focus()
      returnToId.current = null
    } else if (selectedId === null && focusList.current) {
      listRef.current?.focus()
      focusList.current = false
    }
  }, [selectedId, items])

  function backToList() {
    returnToId.current = selectedId
    setSelectedId(null)
  }

  async function remove(id?: string) {
    if (busy) return
    if (!id && !window.confirm('清空此设备上当前用户的全部收藏？')) return
    setBusy(true); setError(null)
    try {
      if (id) { await deleteSnapshot(userId, id, databaseName); focusList.current = true; setItems((current) => current.filter((item) => item.id !== id)); setSelectedId(null) }
      else { await clearSnapshots(userId, databaseName); focusList.current = true; setItems([]); setSelectedId(null) }
    } catch { setError('删除失败，请重试。') } finally { setBusy(false) }
  }

  const selectedCard = selected ? cardSchema.safeParse(selected.card) : null
  if (selected) return <section onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); backToList() } }}>
    <button type="button" autoFocus onClick={backToList} className="mb-4 inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm text-jade-800 hover:bg-jade-50"><ArrowLeft size={16} />返回收藏</button>
    <IntelligentCard value={selected.card} hidden={hidden} />
    {selectedCard?.success && selectedCard.data.origin && onOpenSource && <button type="button" disabled={sourceDisabled} onClick={() => onOpenSource(selectedCard.data.origin!)} className="mt-3 rounded-lg px-2 py-2 text-sm text-jade-800 underline disabled:opacity-50">查看来源会话</button>}
    {selectedCard?.success && selectedCard.data.origin && onOpenSource && sourceDisabled && <p className="mt-1 text-xs text-muted">请先处理当前请求或操作，再查看来源会话。</p>}
    {selectedCard?.success && !selectedCard.data.origin && <p role="status" className="mt-3 text-sm text-muted">此收藏未保存会话来源，无法定位到原始消息。</p>}
    {selectedCard?.success && selectedCard.data.origin && !onOpenSource && <p role="status" className="mt-3 text-sm text-muted">此处无法打开已保存的来源消息。</p>}
    <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted"><span>{selected.savedAt ? `收藏于 ${new Date(selected.savedAt).toLocaleString('zh-CN')}` : '收藏时间未知'}</span><button type="button" disabled={busy} onClick={() => void remove(selected.id)} className="min-h-10 rounded-lg px-2 text-red-700 underline disabled:opacity-50">删除</button></div>
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
  </section>

  return <section ref={listRef} tabIndex={-1} aria-label="收藏列表">
    <div className="flex items-start justify-between gap-3"><p className="min-w-0 flex-1 text-sm leading-5 text-muted">仅保存在此设备，不会自动更新；部分敏感文字可能保留。</p>{items.length > 0 && <button type="button" disabled={busy} onClick={() => void remove()} className="min-h-10 shrink-0 whitespace-nowrap px-2 text-sm text-muted underline disabled:opacity-50">清空</button>}</div>
    {loading && <p role="status" className="mt-5 text-sm text-muted">加载中…</p>}
    {error && <p role="alert" className="mt-5 text-sm text-red-700">{error}</p>}
    {!loading && !error && items.length === 0 && <div className="mt-6"><MascotEmptyState title="还没有收藏卡片" description="喜欢的分析结果，可以收藏在这里。" pose="peek" /></div>}
    <div className="mt-5 space-y-3">{items.map((item, index) => {
      const parsed = cardSchema.safeParse(item.card)
      const title = hidden ? `收藏 ${index + 1} 已隐藏` : parsed.success ? parsed.data.title : '此卡片数据无法展示'
      return <button key={item.id} ref={(element) => { if (element) itemButtons.current.set(item.id, element); else itemButtons.current.delete(item.id) }} type="button" onClick={() => setSelectedId(item.id)} className="flex w-full items-center gap-3 rounded-2xl border border-line bg-white px-4 py-4 text-left hover:bg-jade-50/50 focus-visible:outline-2 focus-visible:outline-jade-700">
        <span className="min-w-0 flex-1"><span className="block break-words text-sm font-medium">{title}</span><span className="mt-1 block text-xs text-muted">{item.savedAt ? `收藏于 ${new Date(item.savedAt).toLocaleString('zh-CN')}` : '收藏时间未知'}</span></span><ChevronRight size={16} className="shrink-0 text-muted" />
      </button>
    })}</div>
  </section>
}
