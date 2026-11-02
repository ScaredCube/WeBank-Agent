import { formatCnyFen } from '@/lib/format'
import { subscriptionResultSchema } from './subscription-schema'
export function SubscriptionResult({ value, hidden }: { value: unknown; hidden: boolean }) {
  const parsed = subscriptionResultSchema.safeParse(value)
  if (!parsed.success) return <p role="status" className="text-sm text-muted">订阅结果暂时无法展示。</p>
  const item = parsed.data
  return <section className="rounded-2xl border border-line p-4"><h3 className="font-semibold">{item.kind === 'subscriptions' ? '订阅' : '疑似重复扣款'}</h3>{item.kind === 'subscription_candidates' && <p className="mt-1 text-xs text-muted">仅供核对，不能据此认定重复扣款。</p>}{item.data.length === 0 ? <p className="mt-2 text-sm text-muted">暂无记录</p> : <ul className="mt-2 divide-y divide-line">{item.data.map((row, i) => <li key={i} className="flex justify-between gap-3 py-2 text-sm"><span>{hidden ? '••••' : row.merchant}</span><span>{hidden ? '••••' : formatCnyFen(row.amount_fen)}</span></li>)}</ul>}</section>
}
