import { ArrowUpRight, Eye, EyeOff } from 'lucide-react'

import type { HomeOverview } from '@/features/home/useHomeAccountOverview'
import { formatCnyFen } from '@/lib/format'

interface HomeAccountSummaryProps {
  overview: HomeOverview
  hidden: boolean
  onTogglePrivacy?: () => void
  onOpenAssets?: () => void
}

/** Compact bank facts, not an invented dashboard. */
export function HomeAccountSummary({ overview, hidden, onTogglePrivacy, onOpenAssets }: HomeAccountSummaryProps) {
  const accounts = overview.data?.accounts ?? []
  const queriedAt = overview.data?.generated_at
  const queryTime = queriedAt && !Number.isNaN(Date.parse(queriedAt))
    ? new Date(queriedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : null

  return (
    <section aria-label="账户速览" className="border-t border-line pt-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h3 className="text-[13px] font-semibold text-ink">账户速览</h3>
          <span className="text-[10px] tabular-nums text-muted">{overview.status === 'ready' ? accounts.length + ' 个账户' : '—'}</span>
        </div>
        <div className="flex items-center gap-2">
          {onTogglePrivacy && <button type="button"
            onClick={onTogglePrivacy}
            aria-label={hidden ? '显示金额' : '隐藏金额'}
            title={hidden ? '显示金额' : '隐藏金额'}
            aria-pressed={hidden}
            className="grid size-10 place-items-center rounded-full text-muted transition-colors hover:bg-jade-50 hover:text-jade-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700"
          >{hidden ? <EyeOff size={17} /> : <Eye size={17} />}</button>}
          {onOpenAssets && <button type="button" onClick={onOpenAssets}
            className="flex min-h-10 items-center gap-2 rounded-md px-2 text-[12px] font-medium text-jade-800 transition-colors hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700">
            全部资产 <ArrowUpRight aria-hidden="true" size={15} />
          </button>}
        </div>
      </div>

      <div className="mt-4 min-h-[100px]">
        {overview.status === 'loading' && <p role="status" className="py-7 text-[13px] text-muted">正在获取模拟账户信息…</p>}
        {overview.status === 'error' && <p role="status" className="py-7 text-[13px] text-muted">账户信息暂不可用</p>}
        {overview.status === 'ready' && accounts.length === 0 && <p className="py-7 text-[13px] text-muted">暂无可展示的账户</p>}
        {overview.status === 'ready' && accounts.length > 0 && (
          <div className="grid border-t border-line md:grid-cols-2 md:divide-x md:divide-line">
            {accounts.slice(0, 2).map((account, index) => (
              <div key={account.account_id} className="border-b border-line py-4 md:border-b-0 md:px-6 md:first:pl-0">
                <div className="flex items-center justify-between gap-4 text-[11px] text-muted">
                  <span className="truncate">{hidden ? '账户 ' + (index + 1) : account.name}</span>
                  <span className="font-mono tracking-[0.05em]">{hidden ? '••••' : account.masked_number}</span>
                </div>
                <div className="mt-3 flex items-baseline justify-between gap-3">
                  <p aria-label={hidden ? '金额已隐藏' : account.currency === 'CNY' ? formatCnyFen(account.balance_fen) : '非人民币账户'}
                    className="min-w-0 break-all text-[clamp(1.45rem,2.3vw,2rem)] font-semibold tracking-[-0.047em] tabular-nums text-ink">
                    {hidden ? '••••••' : account.currency === 'CNY' ? formatCnyFen(account.balance_fen) : '—'}
                  </p>
                  <span className="shrink-0 text-[10px] text-muted">{account.currency}</span>
                </div>
              </div>
            ))}
            {accounts.length > 2 && <span className="self-center px-4 py-3 text-[12px] text-muted">另有 {accounts.length - 2} 个账户</span>}
          </div>
        )}
      </div>
      <p className="mt-3 text-[10px] leading-5 text-muted/70">
        {queryTime ? '模拟银行数据 · 查询于 ' + queryTime : '模拟银行数据 · 以实际查询结果为准'}
      </p>
    </section>
  )
}
