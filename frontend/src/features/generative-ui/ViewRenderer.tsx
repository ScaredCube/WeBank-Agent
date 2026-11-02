import { createContext, useContext, type ReactNode } from 'react'
import { defineRegistry, JSONUIProvider, Renderer } from '@json-render/react'
import { catalog } from './catalog'
import { formatCnyFen } from '@/lib/format'
import type { ViewEnvelope } from './view'

type Context = { view: ViewEnvelope; hidden: boolean; busy: boolean; interactive: boolean; canOpen: boolean; interact: (action: string, value?: unknown) => void; open: () => void; follow: () => void; source: () => void }
const ViewContext = createContext<Context | null>(null)
function useView() { const value = useContext(ViewContext); if (!value) throw new Error('missing view context'); return value }
function display(value: string | number | boolean | null | undefined, format: string, hidden: boolean): string {
  if (hidden) return '••••'
  if (value == null) return '—'
  if (format === 'currency' && typeof value === 'number') return formatCnyFen(value)
  if (format === 'percent' && typeof value === 'number') return `${value}%`
  return String(value)
}
const titles: Record<string, string> = { overview: '概览', categories: '消费分类', comparison: '对比', subscriptions: '订阅', candidates: '疑似重复扣款', anomalies: '待核对' }
function Dataset({ id, type }: { id: string; type: string }) {
  const { view, hidden, interact, busy, interactive } = useView()
  const data = view.trusted_data.datasets[id]
  const state = view.interaction_state
  const rows = data.rows.filter(row => data.kind !== 'subscriptions' || state.filter === 'all' || (state.filter === 'active' ? row.status === '生效中' : row.renewal_status === '即将续费'))
  const amountColumn = data.columns.find(c => c.key === 'amount_fen' && c.format === 'currency')
  if (state.sort !== 'default' && amountColumn) rows.sort((a,b) => {
    const left = a[amountColumn.key], right = b[amountColumn.key]
    if (typeof left !== 'number' || typeof right !== 'number') return 0
    return state.sort === 'amount_desc' ? right - left : left - right
  })
  const canSelect = interactive && view.allowed_actions.includes(data.kind === 'categories' ? 'select_category' : 'select_ids')
  if (type === 'CategoryBarChart') {
    const label = data.columns.find(c => c.format === 'text')
    const amount = data.columns.find(c => c.format === 'currency' || c.format === 'number')
    const count = data.columns.find(c => c.key === 'count' && c.format === 'number')
    const selectedRow = state.selected_category
      ? rows.find(row => row.id === state.selected_category)
      : undefined
    const max = amount ? Math.max(0, ...rows.map(row => typeof row[amount.key] === 'number' ? Math.max(0, row[amount.key] as number) : 0)) : 0
    return <section className="space-y-3"><h4 className="text-sm font-semibold">{data.title}</h4>
      {selectedRow && <div role="status" aria-live="polite" className="rounded-xl border border-jade-200 bg-jade-50 px-3 py-2 text-sm text-jade-900">
        <p className="font-medium">已选{display(label ? selectedRow[label.key] : selectedRow.id, 'text', hidden)}</p>
        <p className="mt-1 text-xs">金额 {amount ? display(selectedRow[amount.key], amount.format, hidden) : '—'}{count ? ` · ${display(selectedRow[count.key], count.format, hidden)} 笔` : ''}</p>
      </div>}
      {rows.length === 0 && <p className="text-sm text-muted">暂无数据</p>}{rows.map(row => <div key={row.id} className="space-y-1"><div className="flex justify-between gap-3 text-sm">{canSelect ? <button type="button" disabled={busy} aria-pressed={view.interaction_state.selected_category === row.id} onClick={() => interact('select_category', row.id)} className="min-h-11 rounded-lg px-2 text-jade-800 underline aria-pressed:bg-jade-100 aria-pressed:font-bold aria-pressed:ring-2 aria-pressed:ring-jade-700 disabled:opacity-50">{display(label ? row[label.key] : row.id, 'text', hidden)}</button> : <span>{display(label ? row[label.key] : row.id, 'text', hidden)}</span>}<span>{amount ? display(row[amount.key], amount.format, hidden) : '—'}</span></div>{!hidden && amount && <div className="h-2 rounded-full bg-jade-50" aria-hidden="true"><div className="h-2 rounded-full bg-jade-700" style={{width:`${max && typeof row[amount.key] === 'number' ? Math.max(0, row[amount.key] as number) / max * 100 : 0}%`}}/></div>}</div>)}</section>
  }
  return <section className="space-y-2"><h4 className="text-sm font-semibold">{data.title}</h4>
    {rows.length === 0 ? <p className="text-sm text-muted">暂无数据</p> : <div className="overflow-x-auto"><table className="w-full min-w-0 text-left text-sm"><thead><tr>{data.columns.map(c => <th key={c.key} className="p-2 font-medium text-muted">{c.label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id} className="border-t border-line">{data.columns.map((c, index) => <td key={c.key} className="p-2 break-words">{index === 0 && canSelect && (type === 'SelectableList' || type === 'CategoryBarChart' || type === 'Selector') ? <button type="button" disabled={busy} aria-pressed={data.kind === 'categories' ? view.interaction_state.selected_category === row.id : view.interaction_state.selected_ids.includes(row.id)} onClick={() => interact(data.kind === 'categories' ? 'select_category' : 'select_ids', data.kind === 'categories' ? row.id : view.interaction_state.selected_ids.includes(row.id) ? view.interaction_state.selected_ids.filter(x => x !== row.id) : [...view.interaction_state.selected_ids, row.id])} className="min-h-11 rounded-lg px-2 text-jade-800 underline aria-pressed:bg-jade-100 aria-pressed:font-bold aria-pressed:ring-2 aria-pressed:ring-jade-700 disabled:opacity-50">{display(row[c.key], c.format, hidden)}</button> : display(row[c.key], c.format, hidden)}</td>)}</tr>)}</tbody></table></div>}
  </section>
}
function Controls({ id, type }: { id: string; type: string }) {
  const { view, busy, interact, interactive } = useView()
  if (!interactive) return null
  if (type === 'Filter') return <div className="flex flex-wrap gap-2">{view.trusted_data.datasets[id].kind === 'subscriptions' && view.allowed_actions.includes('set_filter') && <label className="text-sm">筛选 <select disabled={busy} value={view.interaction_state.filter} onChange={e => interact('set_filter', e.target.value)} className="min-h-11 rounded-lg border border-line bg-panel px-2"><option value="all">全部</option><option value="active">进行中</option><option value="renewal_soon">即将续费</option></select></label>}{view.allowed_actions.includes('set_sort') && <label className="text-sm">排序 <select disabled={busy} value={view.interaction_state.sort} onChange={e => interact('set_sort', e.target.value)} className="min-h-11 rounded-lg border border-line bg-panel px-2"><option value="default">默认</option><option value="amount_desc">金额从高到低</option><option value="amount_asc">金额从低到高</option></select></label>}{view.allowed_actions.includes('clear_filters') && <button disabled={busy} onClick={() => interact('clear_filters')} className="min-h-11 text-sm underline">清除筛选</button>}</div>
  return <Dataset id={id} type={type}/>
}
const { registry } = defineRegistry(catalog, { components: {
  Stack: ({ children }) => <div className="space-y-4">{children}</div>,
  Grid: ({ children }) => <div className="grid gap-3 sm:grid-cols-2">{children}</div>,
  Section: ({ props, children }) => <section className="space-y-3 rounded-2xl border border-line bg-panel p-4"><h3 className="font-semibold">{titles[props.title_key]}</h3>{children}</section>,
  Metric: ({ props }) => <Metric id={props.metric_ref}/>,
  MetricComparison: ({ props }) => <Dataset id={props.dataset_ref} type="MetricComparison"/>,
  CategoryBarChart: ({ props }) => <Dataset id={props.dataset_ref} type="CategoryBarChart"/>,
  ComparisonTable: ({ props }) => <Dataset id={props.dataset_ref} type="ComparisonTable"/>,
  RecordList: ({ props }) => <Dataset id={props.dataset_ref} type="RecordList"/>,
  SelectableList: ({ props }) => <Dataset id={props.dataset_ref} type="SelectableList"/>,
  Filter: ({ props }) => <Controls id={props.dataset_ref} type="Filter"/>,
  Selector: ({ props }) => <Controls id={props.dataset_ref} type="Selector"/>,
  ActionLink: ({ props }) => <Link action={props.action}/>,
} })
function Metric({ id }: { id: string }) { const { view, hidden } = useView(); const m = view.trusted_data.metrics[id]; return <div className="rounded-xl bg-canvas p-4"><div className="text-xs text-muted">{m.label}</div><div className="mt-1 text-xl font-semibold">{display(m.value, m.format, hidden)}</div>{m.period && <div className="text-xs text-muted">{m.period}</div>}{m.note && <div className="text-xs text-muted">{m.note}</div>}</div> }
function Link({ action }: { action: string }) { const c = useView(); const actions: Record<string, [string, () => void]> = { open_workspace: ['打开工作区', c.open], view_source: ['查看来源', c.source], follow_up: ['继续分析', c.follow] }; if ((action === 'open_workspace' && !c.canOpen) || (!c.interactive && action !== 'open_workspace')) return null; const [label, click] = actions[action]; return <button type="button" disabled={c.busy} onClick={click} className="min-h-11 text-sm text-jade-800 underline disabled:opacity-50">{label}</button> }
export function ViewRenderer({ view, hidden, busy = false, interact, open, follow = () => {}, source = () => {} }: { view: ViewEnvelope; hidden: boolean; busy?: boolean; interact?: Context['interact']; open?: () => void; follow?: () => void; source?: () => void }): ReactNode {
  return <ViewContext.Provider value={{ view, hidden, busy, interactive: !!interact, canOpen: !!open, interact: interact ?? (() => {}), open: open ?? (() => {}), follow, source }}><JSONUIProvider registry={registry}><Renderer spec={view.spec} registry={registry}/></JSONUIProvider></ViewContext.Provider>
}
