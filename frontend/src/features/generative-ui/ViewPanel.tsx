import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import { ApiError, api } from '@/lib/api'
import { formatCnyFen } from '@/lib/format'
import { parseView, type ViewEnvelope } from './view'
import { ViewRenderer } from './ViewRenderer'

export function ViewPanel({ view, token, hidden, onChange, onClose, onFollow, onSource, onBlockedChange = () => {}, externalBusy = false }: { view: ViewEnvelope; token: string; hidden: boolean; onChange: (v: ViewEnvelope) => void; onClose: () => void; onFollow: () => void; onSource: () => void; onBlockedChange?: (blocked: boolean) => void; externalBusy?: boolean }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function interact(action: string, value?: unknown) {
    if (busy || externalBusy || !view.allowed_actions.some(item => item === action)) return
    setBusy(true); setError(null); onBlockedChange(true)
    try {
      const raw = await api.viewInteraction(token, view.view_id, view.revision, action, value)
      const updated = parseView(raw)
      if (!updated || updated.view_id !== view.view_id || updated.conversation_id !== view.conversation_id) {
        throw new Error('服务器返回的视图数据无效')
      }
      onChange(updated)
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? '视图版本已变化，请重新读取最新版本。' : '保存筛选失败，请重试或重新读取视图。')
    } finally {
      setBusy(false)
      onBlockedChange(false)
    }
  }
  async function reload() {
    if (busy || externalBusy) return
    setBusy(true); setError(null); onBlockedChange(true)
    try {
      const latest = parseView(await api.view(token, view.view_id))
      if (!latest || latest.view_id !== view.view_id || latest.conversation_id !== view.conversation_id) throw new Error()
      onChange(latest)
    }
    catch { setError('无法读取最新视图，请稍后重试。') }
    finally { setBusy(false); onBlockedChange(false) }
  }
  // Stable product affordance: the model chooses the layout, never whether
  // trustworthy category selection remains possible.
  const categoryDataset = Object.values(view.trusted_data.datasets).find(data => data.kind === 'categories' && data.rows.length > 0)
  const renderedCategoryControl = Object.values(view.spec.elements).some(element =>
    (element.type === 'CategoryBarChart' || element.type === 'Selector') &&
    view.trusted_data.datasets[String(element.props.dataset_ref)]?.kind === 'categories'
  )
  const fallbackCategories = view.allowed_actions.includes('select_category') && categoryDataset && !renderedCategoryControl
  const categoryLabelKey = categoryDataset?.columns.find(column => column.format === 'text')?.key
  const categoryAmountKey = categoryDataset?.columns.find(column => column.format === 'currency')?.key
  const categoryCountKey = categoryDataset?.columns.find(column => column.key === 'count' && column.format === 'number')?.key
  const selectedRow = categoryDataset?.rows.find(row => row.id === view.interaction_state.selected_category)
  const selectedAmount = selectedRow && categoryAmountKey ? selectedRow[categoryAmountKey] : undefined
  const selectedCount = selectedRow && categoryCountKey ? selectedRow[categoryCountKey] : undefined
  return <section id="workspace-panel" aria-label="分析工作区" className="absolute inset-0 z-30 flex flex-col bg-workspace xl:relative xl:inset-auto xl:z-auto xl:w-[clamp(400px,36vw,520px)] xl:shrink-0 xl:border-l xl:border-line" onKeyDown={e => { if (e.key === 'Escape') onClose() }}>
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line px-5"><button type="button" autoFocus onClick={onClose} className="grid size-10 place-items-center rounded-lg" aria-label="返回对话"><ArrowLeft size={18}/></button><h2 className="flex-1 font-semibold">分析工作区</h2></header>
    <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-5"><p className="mb-4 text-xs text-muted">数据时间：{new Date(view.observed_at).toLocaleString('zh-CN')} · 历史版本 {view.revision}</p>
      {view.allowed_actions.includes('set_sort') && <label className="mb-4 flex items-center gap-2 text-sm">排序<select disabled={busy || externalBusy || !!error} value={view.interaction_state.sort} onChange={e => void interact('set_sort', e.target.value)} className="min-h-11 rounded-lg border border-line bg-panel px-2"><option value="default">默认</option><option value="amount_desc">金额从高到低</option><option value="amount_asc">金额从低到高</option></select></label>}
      {fallbackCategories && <section aria-label="消费分类选择" className="mb-4 rounded-xl border border-line bg-panel p-3">
        <h3 className="mb-2 text-sm font-medium">选择消费分类</h3>
        <div className="flex flex-wrap gap-2">{categoryDataset.rows.map((row, index) =>
          <button key={row.id} type="button" disabled={busy || externalBusy || !!error}
            aria-pressed={view.interaction_state.selected_category === row.id}
            onClick={() => void interact('select_category', row.id)}
            className="min-h-11 rounded-lg border border-line px-3 text-sm text-jade-800 aria-pressed:bg-jade-100 aria-pressed:font-semibold disabled:opacity-50">
            {hidden ? `分类 ${index + 1}` : String(categoryLabelKey ? row[categoryLabelKey] : row.id)}
          </button>)}</div>
        {selectedRow && <p role="status" className="mt-2 text-xs text-muted">
          已选{hidden ? '分类' : String(categoryLabelKey ? selectedRow[categoryLabelKey] : selectedRow.id)}
          {categoryAmountKey && ` · 金额 ${hidden ? '••••' : typeof selectedAmount === 'number' ? formatCnyFen(selectedAmount) : '—'}`}
          {categoryCountKey && ` · ${hidden ? '••••' : selectedCount} 笔`}
        </p>}
      </section>}
      <ViewRenderer view={view} hidden={hidden} busy={busy || externalBusy || !!error} interact={(action, value) => void interact(action, value)} follow={onFollow} source={onSource}/>
      {busy && <p role="status" className="mt-3 text-sm text-muted">保存中…</p>}
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error} <button type="button" disabled={busy || externalBusy} onClick={() => void reload()} className="underline">重新读取</button></p>}
      <div className="mt-5 flex flex-wrap gap-3"><button type="button" disabled={busy || externalBusy || !!error} onClick={onFollow} className="min-h-11 rounded-xl bg-jade-700 px-4 text-sm text-white disabled:opacity-50">继续分析</button></div>
    </div>
  </section>
}
