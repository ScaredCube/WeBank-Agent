import { cardSchema, type CardAction, type CardDescription } from './schema'
import { formatCnyFen } from '@/lib/format'

const actionLabels: Record<CardAction, string> = { open_assets: '查看资产', open_collections: '查看收藏', open_activity: '查看操作记录' }

export function IntelligentCard({ value, hidden = false, onAction }: { value: unknown; hidden?: boolean; onAction?: (action: CardAction) => void }) {
  const result = cardSchema.safeParse(value)
  if (!result.success) return <div role="alert" className="rounded-2xl border border-line bg-white p-4 text-sm text-muted">此卡片数据无法展示</div>
  const card = result.data
  function renderItem(item: CardDescription['blocks'][number], index: number): React.ReactNode {
    if (item.type === 'group') return <div key={index} className={item.layout === 'columns' ? 'grid grid-cols-1 gap-4 sm:grid-cols-2' : 'space-y-4'}>{item.blocks.map(renderItem)}</div>
    if (item.type === 'text') return <p key={index} className="text-sm leading-relaxed text-muted">{hidden ? <span aria-label="内容已隐藏">••••</span> : item.text}</p>
    if (item.type === 'metric') return <div key={index} className="border-b border-line pb-4"><p className="text-xs font-medium text-muted">{hidden ? '指标' : item.label}</p><p className="mt-1.5 text-[30px] font-semibold leading-none tracking-tight tabular-nums text-ink">{hidden ? <span aria-label="内容已隐藏">••••</span> : formatCnyFen(item.value)}</p></div>
    if (item.type === 'action') return <button type="button" key={index} disabled={!onAction} onClick={() => onAction?.(item.action)} className="rounded-xl border border-jade-200 px-3 py-2 text-sm text-jade-800 disabled:opacity-50">{actionLabels[item.action]}</button>
    if (item.type === 'bar_chart') {
      const max = Math.max(...item.rows.map((row) => row.value), 0)
      return <figure key={index}><figcaption className="mb-3 flex items-baseline justify-between gap-3"><span className="text-sm font-medium">{hidden ? '图表' : item.title}</span>{!hidden && <span className="text-xs text-muted">相对最高项</span>}</figcaption>{hidden ? <span aria-label="图表数值已隐藏" className="text-sm text-muted">••••</span> : <dl className="space-y-2.5">{item.rows.map((row, rowIndex) => <div key={rowIndex}><div className="flex justify-between gap-3 text-xs"><dt className="text-muted">{row.label}</dt><dd className="tabular-nums">{formatCnyFen(row.value)}</dd></div><div className="mt-1 h-1.5 rounded-full bg-jade-50" aria-hidden="true"><div data-testid="chart-bar" className="h-full rounded-full bg-jade-600" style={{ width: `${max === 0 ? 0 : row.value / max * 100}%` }} /></div></div>)}</dl>}</figure>
    }
    return <dl key={index} className="divide-y divide-line">{item.rows.map((row, rowIndex) => <div key={rowIndex} className="flex justify-between gap-3 py-2 text-sm"><dt className="text-muted">{hidden ? '项目' : row.label}</dt><dd className="text-right tabular-nums">{hidden ? <span aria-label="内容已隐藏">••••</span> : row.value}</dd></div>)}</dl>
  }
  return <article className="rounded-[18px] border border-line bg-white px-5 py-4 sm:px-6 sm:py-5">
    <h3 className="text-[15px] font-semibold tracking-tight text-ink">{hidden ? '卡片内容已隐藏' : card.title}</h3>
    <div className="mt-4 space-y-4">{card.blocks.map(renderItem)}</div>
    <p className="mt-4 border-t border-line pt-3 text-xs leading-5 text-muted">{!hidden && <>{card.source} · </>}{new Date(card.observedAt).toLocaleString('zh-CN')}</p>
  </article>
}
