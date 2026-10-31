import { CreditCard, ArrowUpRight, ShieldCheck, ShieldAlert } from 'lucide-react'
import { z } from 'zod'

const statusRow = z.object({
  card_id: z.number().int().safe().positive(),
  account_name: z.string().max(120),
  masked_number: z.string().max(90),
  status: z.string().max(30),
  account_status: z.string().max(30),
})
export const cardStatusSnapshotSchema = z.object({
  cards: z.array(statusRow).max(30),
})

export function CardStatusResult({ value, hidden = false, onOpenAssets }: {
  value: unknown
  hidden?: boolean
  onOpenAssets?: () => void
}) {
  const result = cardStatusSnapshotSchema.safeParse(value)
  if (!result.success) return <p role="alert" className="text-sm text-muted">银行卡状态暂时无法展示，请重新查询。</p>
  const rows = result.data.cards
  return <section aria-label="银行卡状态结果" className="overflow-hidden rounded-[22px] border border-line bg-panel shadow-[0_14px_45px_-40px_rgba(0,38,29,.36)]">
    <header className="flex items-center justify-between px-5 pb-2 pt-5 sm:px-6">
      <h3 className="text-[16px] font-semibold tracking-[-0.025em] text-ink">银行卡状态</h3>
      <CreditCard size={20} className="text-jade-700" aria-hidden="true"/>
    </header>
    {rows.length === 0 ? <p className="px-5 py-8 text-[13px] text-muted sm:px-6">未查询到银行卡。</p> :
      <div className="space-y-4 px-5 py-4 sm:px-6">
        {rows.map(card => {
          const available = card.status === 'active' && card.account_status === 'active'
          const label = card.status === 'lost' ? '已挂失'
            : card.status !== 'active' ? '卡片不可用'
            : card.account_status !== 'active' ? '关联账户不可用' : '状态正常'
          return <div key={card.card_id} className="space-y-3">
            <div className="relative isolate overflow-hidden rounded-[18px] bg-[#143d35] px-5 py-5 text-white shadow-[0_14px_25px_-17px_rgba(0,38,29,.55)]">
              <div className="pointer-events-none absolute -right-9 -top-16 size-52 rounded-full border border-white/15" aria-hidden="true"/>
              <div className="pointer-events-none absolute -right-2 -top-9 size-40 rounded-full border border-white/15" aria-hidden="true"/>
              <div className="relative flex min-h-[110px] flex-col justify-between gap-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="min-w-0 truncate text-[13px] font-semibold tracking-tight">{hidden ? '账户已隐藏' : card.account_name}</span>
                  <CreditCard size={19} className="shrink-0 text-white/80" aria-hidden="true"/>
                </div>
                <p className="text-[18px] font-medium tracking-[0.085em] tabular-nums">{hidden ? '•••• ••••' : card.masked_number}</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 px-1">
              <span className="inline-flex items-center gap-1.5 text-[12px] font-medium text-ink">
                {available ? <ShieldCheck size={15} className="text-jade-700"/> : <ShieldAlert size={15} className="text-amber-600"/>}
                {label}
              </span>
              {!available && <span className="text-xs text-muted">具体可用操作以银行确认结果为准</span>}
            </div>
          </div>
        })}
      </div>}
    <footer className="flex items-center justify-between gap-3 border-t border-line px-5 py-3 sm:px-6">
      <span className="min-w-0 truncate text-[11px] text-muted">来源：银行账户与卡片状态工具</span>
      {onOpenAssets && <button type="button" onClick={onOpenAssets}
        className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-jade-800 hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700">
        查看资产 <ArrowUpRight size={14} aria-hidden="true"/>
      </button>}
    </footer>
  </section>
}
