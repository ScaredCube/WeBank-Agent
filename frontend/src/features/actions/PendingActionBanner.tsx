import { ArrowUpRight, Clock3, ShieldAlert } from 'lucide-react'
import type { StreamEvent } from '@/lib/sse'

type Event = Extract<StreamEvent, { type: 'action_required' }>
const labels: Record<string, string> = {
  transfer: '模拟转账',
  card_loss: '模拟挂失',
  wealth_subscribe: '模拟申购',
  wealth_redeem: '模拟赎回',
  subscription_cancel: '取消订阅',
}

/** Persistent, privacy-safe reminder for an unresolved server action. */
export function PendingActionBanner({ event, onOpen }: { event: Event; onOpen: () => void }) {
  const title = labels[event.action.action_type] ?? '银行操作'
  const expires = Date.parse(event.action.expires_at)
  const time = Number.isFinite(expires)
    ? new Date(expires).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  return <section aria-label="待处理银行操作" className="mx-auto mb-3 w-full max-w-[680px] rounded-2xl border border-jade-200 bg-jade-50/60 px-4 py-3">
    <div className="flex items-start gap-3">
      <span aria-hidden="true" className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-panel text-jade-800">
        <ShieldAlert size={19} strokeWidth={1.8}/>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold text-ink">有一项操作需要你处理</p>
        <p className="mt-1 text-[12px] text-muted">{title} · 尚待核实或完成</p>
        {time && <p className="mt-1 inline-flex items-center gap-1.5 text-[11px] text-muted">
          <Clock3 size={12} aria-hidden="true"/> 有效期至 {time}
        </p>}
      </div>
      <button type="button" onClick={onOpen}
        className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl border border-line bg-panel px-3 text-[12px] font-semibold text-jade-800 transition-colors hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700">
        查看待处理操作 <ArrowUpRight size={14} aria-hidden="true"/>
      </button>
    </div>
  </section>
}
