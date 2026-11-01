import { Check } from 'lucide-react'
import type { StreamEvent } from '@/lib/sse'
import { Money } from '@/features/privacy/Money'

type Event = Extract<StreamEvent, { type: 'action_required' }>

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null
}

export function CompletedActionCard({ event }: { event: Event }) {
  const action = event.action
  const details = action.details
  const amount = typeof details.amount_fen === 'number' && Number.isSafeInteger(details.amount_fen)
    ? details.amount_fen : null
  const rows: [string, string][] = []
  if (action.action_type === 'transfer') {
    const account = text(details.account_masked)
    const recipient = text(details.recipient_name)
    if (account) rows.push(['付款', account])
    if (recipient) rows.push(['收款', recipient])
  } else if (action.action_type === 'internal_transfer') {
    const source = text(details.source_masked)
    const target = text(details.target_masked)
    if (source) rows.push(['转出', source])
    if (target) rows.push(['转入', target])
  } else if (action.action_type === 'collection_request') {
    const payer = text(details.contact_name)
    const account = text(details.account_masked)
    if (payer) rows.push(['付款人', payer])
    if (account) rows.push(['收款', account])
  } else if (action.action_type === 'wealth_convert') {
    const source = text(details.source_product_name)
    const target = text(details.target_product_name)
    if (source) rows.push(['转出产品', source])
    if (target) rows.push(['转入产品', target])
  } else if (action.action_type === 'wealth_subscribe' || action.action_type === 'wealth_redeem') {
    const product = text(details.product_name)
    if (product) rows.push(['产品', product])
    const account = text(details.account_masked)
    if (account) rows.push(['账户', account])
  } else if (action.action_type === 'card_loss') {
    const card = text(details.masked_number)
    if (card) rows.push(['卡片', card])
  } else if (action.action_type === 'subscription_cancel') {
    const merchant = text(details.merchant)
    if (merchant) rows.push(['服务', merchant])
  }
  const note = text(details.note)
  if (note) rows.push(['备注', note])
  const title = action.action_type === 'collection_request' ? '收款请求已发送'
    : action.action_type === 'card_loss' ? '挂失已完成'
      : action.action_type === 'wealth_subscribe' ? '申购已受理'
        : action.action_type === 'wealth_redeem' ? '赎回已受理'
          : action.action_type === 'wealth_convert' ? '转换已完成'
            : action.action_type === 'subscription_cancel' ? '订阅已取消'
              : action.action_type === 'internal_transfer' ? '内部转账完成' : '转账成功'
  return <article aria-label="操作完成结果" className="rounded-2xl border border-jade-200 bg-white px-4 py-4 shadow-[0_12px_30px_-26px_rgba(0,40,31,.35)]">
    <div className="flex items-start gap-3">
      <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-jade-50 text-jade-700"><Check size={17} /></span>
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold text-ink">{title}</p>
        {amount !== null && <p className="mt-0.5 text-[22px] font-semibold tracking-tight text-ink"><Money fen={amount} peekKey={`completed:${action.id}`} /></p>}
        {rows.length > 0 && <dl className="mt-2 space-y-1 text-[11px]">
          {rows.map(([label, value]) => <div key={label} className="flex justify-between gap-4"><dt className="text-muted">{label}</dt><dd className="text-right text-ink">{value}</dd></div>)}
        </dl>}
        <p className="mt-2 text-[10px] text-muted">服务端已确认完成 · 刷新后以操作记录为准</p>
      </div>
    </div>
  </article>
}
