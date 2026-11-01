import type { ReactNode } from 'react'
import { ArrowUpRight, Clock3 } from 'lucide-react'
import { FinanceSticker, type StickerKind } from '@/features/theme/FinanceSticker'
import { formatCnyFen } from '@/lib/format'
import { cardSchema, type CardAction, type CardDescription } from './schema'

const actionLabels: Record<CardAction, string> = {
  open_assets: '查看资产',
  open_collections: '查看收藏',
  open_activity: '查看操作记录',
}

function cardArtwork(card: CardDescription): StickerKind {
  const blocks = card.blocks.flatMap(block => block.type === 'group' ? block.blocks : [block])
  if (blocks.some(block => block.type === 'bar_chart')) return 'chart'
  if (blocks.some(block => block.type === 'action' && block.action === 'open_assets')) return 'card'
  if (blocks.some(block => block.type === 'metric')) return 'receipt'
  return 'shield'
}

interface CardProps {
  value: unknown
  hidden?: boolean
  onAction?: (action: CardAction) => void
}

export function IntelligentCard({ value, hidden = false, onAction }: CardProps) {
  const result = cardSchema.safeParse(value)
  if (!result.success) return <div role="alert" className="rounded-2xl border border-line bg-panel p-4 text-sm text-muted">此卡片数据无法展示</div>

  const card = result.data
  function renderBlock(item: CardDescription['blocks'][number], index: number): ReactNode {
    if (item.type === 'group') return <div key={index} className={item.layout === 'columns'
      ? 'grid grid-cols-1 gap-x-7 gap-y-5 sm:grid-cols-2'
      : 'space-y-5'}>{item.blocks.map(renderBlock)}</div>

    if (item.type === 'text') return <p key={index} className="text-[13px] leading-7 text-muted">
      {hidden ? <span aria-label="内容已隐藏">••••</span> : item.text}
    </p>

    if (item.type === 'metric') return <div key={index} className="min-w-0 border-l-[3px] border-jade-300 py-1 pl-4">
      <p className="text-[12px] font-medium text-muted">{hidden ? '指标' : item.label}</p>
      <p className="mt-2 break-words text-[clamp(1.5rem,3vw,2.05rem)] font-semibold leading-[1.2] tracking-[-0.045em] tabular-nums text-ink">
        {hidden ? <span aria-label="内容已隐藏">••••</span> : formatCnyFen(item.value)}
      </p>
    </div>

    if (item.type === 'action') return <button type="button" key={index} disabled={!onAction}
      onClick={() => onAction?.(item.action)}
      className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-line bg-panel px-4 text-[12px] font-semibold text-jade-800 transition-colors hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 disabled:opacity-50">
      {actionLabels[item.action]} <ArrowUpRight size={15} aria-hidden="true"/>
    </button>

    if (item.type === 'bar_chart') {
      const max = Math.max(...item.rows.map(row => row.value), 0)
      return <figure key={index} className="rounded-[16px] border border-line/80 bg-canvas/50 px-4 py-4 sm:px-5">
        <figcaption className="mb-5 flex items-baseline justify-between gap-3">
          <span className="text-[13px] font-semibold text-ink">{hidden ? '图表' : item.title}</span>
          {!hidden && <span className="text-[10.5px] text-muted">按金额比较</span>}
        </figcaption>
        {hidden ? <span aria-label="图表数值已隐藏" className="text-sm text-muted">••••</span> : <dl className="space-y-[15px]">
          {item.rows.map((row, rowIndex) => <div key={rowIndex}>
            <div className="flex items-baseline justify-between gap-3 text-[12px]">
              <dt className="font-medium text-muted">{row.label}</dt>
              <dd className="font-medium tabular-nums text-ink">{formatCnyFen(row.value)}</dd>
            </div>
            <div className="mt-2 h-[7px] overflow-hidden rounded-full bg-jade-100/80" aria-hidden="true">
              <div data-testid="chart-bar" className="h-full rounded-full bg-jade-600"
                style={{ width: `${max === 0 ? 0 : row.value / max * 100}%`, opacity: Math.max(0.62, 1 - rowIndex * 0.075) }}/>
            </div>
          </div>)}
        </dl>}
      </figure>
    }

    return <dl key={index} className="divide-y divide-line">
      {item.rows.map((row, rowIndex) => <div key={rowIndex} className="flex items-start justify-between gap-4 py-3 text-[13px]">
        <dt className="shrink-0 text-muted">{hidden ? '项目' : row.label}</dt>
        <dd className="min-w-0 break-words text-right font-medium tabular-nums text-ink">
          {hidden ? <span aria-label="内容已隐藏">••••</span> : row.value}
        </dd>
      </div>)}
    </dl>
  }

  return <article data-intelligent-card="" className="relative overflow-hidden rounded-[21px] border border-line bg-panel shadow-[0_14px_45px_-40px_rgba(0,38,29,.36)]">
    <header className="flex items-center justify-between gap-4 border-b border-line px-5 py-4 sm:px-6">
      <div className="min-w-0">
        <h3 className="truncate text-[16px] font-semibold tracking-[-0.025em] text-ink">
          {hidden ? '卡片内容已隐藏' : card.title}
        </h3>
      </div>
      <span className="grid size-12 shrink-0 place-items-center rounded-[14px] bg-jade-50/50">
        <FinanceSticker kind={cardArtwork(card)} className="size-9"/>
      </span>
    </header>

    <div className="space-y-6 px-5 py-5 sm:px-6 sm:py-6">{card.blocks.map(renderBlock)}</div>
    <footer className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-5 py-3.5 text-[11px] leading-5 text-muted sm:px-6">
      <span className="font-medium">{hidden ? '来源信息已隐藏' : card.source}</span>
      <span aria-hidden="true" className="size-1 rounded-full bg-muted/45"/>
      <span className="inline-flex items-center gap-1.5">
        <Clock3 size={12} aria-hidden="true"/>
        {new Date(card.observedAt).toLocaleString('zh-CN')}
      </span>
    </footer>
  </article>
}
