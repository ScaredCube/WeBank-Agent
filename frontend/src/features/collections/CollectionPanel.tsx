import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ChevronRight, MessageCircle, RefreshCw, Trash2,  } from 'lucide-react'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import { cardSchema, type CardOrigin } from '@/features/intelligent-ui/schema'
import { billResultCard } from '@/features/intelligent-ui/bill-result-card'
import { api } from '@/lib/api'
import { clearSnapshots, deleteSnapshot, listSnapshots, refreshSnapshot, type Snapshot } from './store'

export function CollectionPanel({ userId, hidden, token, onStartChat, databaseName, onOpenSource, sourceDisabled = false }: { userId: number; hidden: boolean; token?: string; onStartChat?: () => void; databaseName?: string; onOpenSource?: (origin: CardOrigin) => void; sourceDisabled?: boolean }) {
  return <UserCollection key={`${databaseName ?? 'default'}:${userId}`} userId={userId} hidden={hidden} token={token} onStartChat={onStartChat} databaseName={databaseName} onOpenSource={onOpenSource} sourceDisabled={sourceDisabled} />
}

function UserCollection({ userId, hidden, token, onStartChat, databaseName, onOpenSource, sourceDisabled }: { userId: number; hidden: boolean; token?: string; onStartChat?: () => void; databaseName?: string; onOpenSource?: (origin: CardOrigin) => void; sourceDisabled: boolean }) {
  const [items, setItems] = useState<Snapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [refreshingId, setRefreshingId] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
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

  async function refreshCard(item: Snapshot) {
    if (!item.refresh || !token || refreshingId || busy) return
    setError(null); setNotice(null); setRefreshingId(item.id)
    try {
      const raw = await api.monthlyBill(token, item.refresh.month, item.refresh.accountId)
      const card = billResultCard(raw)
      if (!card) throw new Error('银行返回的账单格式无效')
      const updated = await refreshSnapshot(userId, item.id, card, databaseName)
      setItems(current => current.map(row => row.id === item.id ? updated : row))
      setNotice('已重新读取银行数据')
    } catch {
      setError('刷新失败，已保留上次成功的数据；请检查账户状态后重试。')
    } finally { setRefreshingId(null) }
  }

  const selectedCard = selected ? cardSchema.safeParse(selected.card) : null
  if (selected) return <section onKeyDown={(event) => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); backToList() } }}>
    <button type="button" autoFocus onClick={backToList} className="mb-4 inline-flex min-h-10 items-center gap-2 rounded-lg px-2 text-sm text-jade-800 hover:bg-jade-50"><ArrowLeft size={16} />返回收藏</button>
    <div className="mb-3 flex flex-wrap items-center justify-between gap-2"><span className="text-xs text-muted">{selected.refresh ? '可从银行重新查询' : '已收藏的历史版本'}</span>
      {selected.refresh && token && <button type="button" disabled={!!refreshingId || busy} onClick={() => void refreshCard(selected)} className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-sm font-medium text-jade-800 disabled:opacity-50"><RefreshCw size={15} className={refreshingId === selected.id ? 'animate-spin' : ''}/>{refreshingId === selected.id ? '更新中…' : '更新数据'}</button>}
    </div>
    <IntelligentCard value={selected.card} hidden={hidden} />
    {notice && <p role="status" className="mt-3 text-sm text-jade-800">{notice}</p>}
    {selectedCard?.success && selectedCard.data.origin && onOpenSource && <button type="button" disabled={sourceDisabled} onClick={() => onOpenSource(selectedCard.data.origin!)} className="mt-3 rounded-lg px-2 py-2 text-sm text-jade-800 underline disabled:opacity-50">查看来源会话</button>}
    {selectedCard?.success && selectedCard.data.origin && onOpenSource && sourceDisabled && <p className="mt-1 text-xs text-muted">请先处理当前请求或操作，再查看来源会话。</p>}
    {selectedCard?.success && !selectedCard.data.origin && <p role="status" className="mt-3 text-sm text-muted">此收藏未保存会话来源，无法定位到原始消息。</p>}
    {selectedCard?.success && selectedCard.data.origin && !onOpenSource && <p role="status" className="mt-3 text-sm text-muted">此处无法打开已保存的来源消息。</p>}
    <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted"><span>{selected.savedAt ? `收藏于 ${new Date(selected.savedAt).toLocaleString('zh-CN')}` : '收藏时间未知'}</span><button type="button" disabled={busy || !!refreshingId} onClick={() => void remove(selected.id)} className="inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-red-700 disabled:opacity-50"><Trash2 size={14}/>删除</button></div>
    {error && <p role="alert" className="mt-4 text-sm text-red-700">{error}</p>}
  </section>

  return <section ref={listRef} tabIndex={-1} aria-label="收藏列表">
    <div className="mb-5 flex items-start justify-between gap-3"><div className="min-w-0 flex-1"><h3 className="text-xl font-semibold tracking-tight text-ink">我的智能卡片</h3><p className="mt-1 text-xs leading-5 text-muted">收藏保存在此浏览器，包含账单金额且未加密；隐藏金额只影响显示。退出登录后仍保留，可随时清空。</p></div>{items.length > 0 && <button type="button" disabled={busy} onClick={() => void remove()} className="min-h-10 shrink-0 whitespace-nowrap px-2 text-sm text-muted underline disabled:opacity-50">清空</button>}</div>
    {loading && <p role="status" className="mt-5 text-sm text-muted">加载中…</p>}
    {error && <p role="alert" className="mt-5 text-sm text-red-700">{error}</p>}
    {!loading && items.length === 0 && <div className="mt-6 rounded-3xl border border-line bg-panel p-6 sm:p-8"><div className="flex flex-col items-center gap-4 text-center"><MascotEmptyState title="还没有收藏卡片" description="从对话中的金融结果卡开始，建立属于你的空间。" pose="peek" />{onStartChat && <button type="button" onClick={onStartChat} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-jade-700 px-5 text-sm font-semibold text-white"><MessageCircle size={17}/>去对话获取卡片</button>}</div></div>}
    <div className="mt-5 grid gap-3 lg:grid-cols-2">{items.map((item, index) => {
      const parsed = cardSchema.safeParse(item.card)
      const title = hidden ? `收藏 ${index + 1} 已隐藏` : parsed.success ? parsed.data.title : '此卡片数据无法展示'
      return <button key={item.id} ref={(element) => { if (element) itemButtons.current.set(item.id, element); else itemButtons.current.delete(item.id) }} type="button" onClick={() => setSelectedId(item.id)} className="flex min-h-[124px] w-full items-center gap-3 rounded-[20px] border border-line bg-panel px-5 py-5 text-left hover:border-jade-300 hover:shadow-[0_10px_25px_-24px_rgba(0,40,30,.4)] focus-visible:outline-2 focus-visible:outline-jade-700">
        <span className="min-w-0 flex-1"><span className="block break-words text-sm font-medium">{title}</span><span className="mt-2 block text-xs text-muted">{item.refresh ? '可更新数据' : '历史版本'} · {item.savedAt ? new Date(item.savedAt).toLocaleDateString('zh-CN') : '收藏时间未知'}</span></span><ChevronRight size={16} className="shrink-0 text-muted" />
      </button>
    })}</div>
  </section>
}
