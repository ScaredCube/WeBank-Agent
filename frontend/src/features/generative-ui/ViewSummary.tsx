import { formatCnyFen } from '@/lib/format'
import type { ViewEnvelope } from './view'

export function ViewSummary({
  view,
  hidden,
  hasOriginal,
  onOpen,
  onOpenOriginal,
}: {
  view: ViewEnvelope
  hidden: boolean
  hasOriginal: boolean
  onOpen: () => void
  onOpenOriginal: () => void
}) {
  const datasets = Object.values(view.trusted_data.datasets)
  const title = datasets[0]?.title ?? '交互式分析'
  const metric = Object.values(view.trusted_data.metrics)[0]
  const categoryData = datasets.find(dataset => dataset.kind === 'categories')
  const labelColumn = categoryData?.columns.find(column => column.format === 'text')
  const amountColumn = categoryData?.columns.find(column => column.format === 'currency')
  const topCategory = categoryData && labelColumn && amountColumn
    ? [...categoryData.rows].sort((left, right) => {
        const leftAmount = left[amountColumn.key]
        const rightAmount = right[amountColumn.key]
        return typeof leftAmount === 'number' && typeof rightAmount === 'number'
          ? rightAmount - leftAmount
          : 0
      })[0]
    : undefined

  return <section aria-label="交互式分析摘要" className="max-w-[560px] rounded-2xl border border-jade-200/80 bg-jade-50/70 p-4">
    <h3 className="text-sm font-semibold text-ink">{title}</h3>
    {(metric || (topCategory && labelColumn && amountColumn)) && <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
      {metric && <span>{metric.label}：{hidden ? '••••' : metric.value == null ? '—' : metric.format === 'currency' ? formatCnyFen(metric.value) : `${metric.value}${metric.format === 'percent' ? '%' : ''}`}</span>}
      {topCategory && labelColumn && amountColumn && <span>主要分类：{hidden ? '••••' : String(topCategory[labelColumn.key] ?? '—')} · {hidden ? '••••' : typeof topCategory[amountColumn.key] === 'number' ? formatCnyFen(topCategory[amountColumn.key] as number) : '—'}</span>}
      {datasets.some(dataset => dataset.kind === 'candidates') && <span>含待核对项目</span>}
    </div>}
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" onClick={onOpen} className="min-h-10 rounded-xl bg-jade-800 px-3 text-xs font-medium text-white hover:bg-jade-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-800">打开工作区</button>
      {hasOriginal && <button type="button" onClick={onOpenOriginal} className="min-h-10 rounded-xl border border-line bg-panel px-3 text-xs text-jade-800 hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-800">查看原始版本</button>}
    </div>
  </section>
}
