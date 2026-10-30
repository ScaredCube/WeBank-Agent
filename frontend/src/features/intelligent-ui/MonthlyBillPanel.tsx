import { useState, type FormEvent } from 'react'
import { z } from 'zod'

import { saveSnapshot } from '@/features/collections/store'
import type { BankAccountOverview } from '@/lib/api'
import { api } from '@/lib/api'
import { formatCnyFen } from '@/lib/format'
import { IntelligentCard } from './Renderer'
import type { CardDescription } from './schema'

const fen = z.number().int().safe().nonnegative()
const count = z.number().int().safe().nonnegative()
const billSchema = z.object({
  month: z.string().regex(/^[0-9]{4}-(0[1-9]|1[0-2])$/),
  account_name: z.string().max(200),
  masked_number: z.string().max(100),
  currency: z.literal('CNY'),
  income_fen: fen,
  expense_fen: fen,
  consumption_fen: fen,
  consumption_count: count,
  transfer_out_fen: fen,
  transfer_out_count: count,
  transfer_in_fen: fen,
  transfer_in_count: count,
  investment_out_fen: fen,
  investment_out_count: count,
  investment_in_fen: fen,
  investment_in_count: count,
  categories: z.array(z.object({ category: z.string().max(200), amount_fen: fen, count })).max(100),
  anomalies: z.array(z.object({ status: z.literal('需核对').optional(), reason: z.string().max(200), counterparty: z.string().max(200), amount_fen: fen, occurred_at: z.iso.datetime({ offset: true }), previous_occurred_at: z.iso.datetime({ offset: true }) })).max(100),
  ignored_count: count,
})

function currentBeijingMonth(): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
  const year = parts.find((part) => part.type === 'year')?.value
  const month = parts.find((part) => part.type === 'month')?.value
  return year && month ? `${year}-${month}` : ''
}

function billTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}

function queryTimestamp(): string {
  return new Date().toISOString()
}

function queryErrorMessage(error: unknown): string {
  const message = error instanceof Error ? error.message : '账单查询失败，请稍后重试。'
  if (message.includes('请指定要查询的账户')) return '当前有多个可用账户。请重试资产加载并选择账单账户后再查询。'
  if (message === '账户不可用') return '所选账户当前不可用于账单查询，请刷新账户数据后重试。'
  return message
}

function emptyAccountMessage(accounts: BankAccountOverview[]): string {
  if (accounts.length === 0) return '暂无可用账户，无法查询月度账单。'
  if (!accounts.some((account) => account.status === 'active')) return '没有状态正常的账户可查询账单。'
  return '当前账单界面仅支持人民币账户；其他币种暂不能查询。'
}

export function MonthlyBillPanel({ token, userId, hidden, accounts = null, accountListLoading = false, accountListError = null }: {
  token: string
  userId: number
  hidden: boolean
  accounts?: BankAccountOverview[] | null
  accountListLoading?: boolean
  accountListError?: string | null
}) {
  const [month, setMonth] = useState(currentBeijingMonth)
  const [selectedAccountId, setSelectedAccountId] = useState('')
  const [card, setCard] = useState<CardDescription | null>(null)
  const [cardAccount, setCardAccount] = useState<{ name: string; maskedNumber: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const billAccounts = accounts?.filter((account) => account.status === 'active' && account.currency === 'CNY')
  const selectedAccount = billAccounts?.find((account) => String(account.account_id) === selectedAccountId)
  const accountId = billAccounts?.length === 1 ? billAccounts[0].account_id : selectedAccount?.account_id
  const accountRequired = billAccounts !== null && billAccounts !== undefined && billAccounts.length > 1 && !selectedAccount
  const noAvailableAccounts = billAccounts !== null && billAccounts !== undefined && billAccounts.length === 0
  const queryDisabled = loading || saving || accountListLoading || accountRequired || noAvailableAccounts

  function resetResult() {
    setCard(null)
    setCardAccount(null)
    setSaved(false)
    setError(null)
  }

  function changeAccount(value: string) {
    setSelectedAccountId(value)
    resetResult()
  }

  async function query(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (queryDisabled) return
    setLoading(true)
    setError(null)
    try {
      const raw = await api.monthlyBill(token, month || undefined, accountId)
      const parsed = billSchema.safeParse(raw)
      if (!parsed.success) throw new Error('账单数据格式不符合预期，请重试查询。')
      const bill = parsed.data
      const blocks: CardDescription['blocks'] = [
        { type: 'metric', label: '总流出 · 含转账和理财申购', value: bill.expense_fen, unit: 'CNY_FEN' },
        { type: 'list', rows: [
          { label: '总流入 · 含转账和理财赎回', value: formatCnyFen(bill.income_fen) },
          { label: `消费 · ${bill.consumption_count} 笔`, value: formatCnyFen(bill.consumption_fen) },
          { label: `转账转出 · ${bill.transfer_out_count} 笔`, value: formatCnyFen(bill.transfer_out_fen) },
          { label: `转账转入 · ${bill.transfer_in_count} 笔`, value: formatCnyFen(bill.transfer_in_fen) },
          { label: `理财申购 · ${bill.investment_out_count} 笔`, value: formatCnyFen(bill.investment_out_fen) },
          { label: `理财赎回 · ${bill.investment_in_count} 笔`, value: formatCnyFen(bill.investment_in_fen) },
        ] },
        { type: 'text', text: '账单按账户现金流统计；消费分类不含转账和理财资金流，理财赎回转入不代表投资收益。' },
        ...(bill.categories.length === 0
          ? [{ type: 'text' as const, text: '本月暂无消费分类。' }]
          : bill.categories.length <= 12
            ? [{ type: 'bar_chart' as const, title: '消费分类', rows: bill.categories.map((item) => ({ label: `${item.category} · ${item.count} 笔`, value: item.amount_fen })) }]
            : [{ type: 'list' as const, rows: bill.categories.map((item) => ({ label: item.category, value: `${formatCnyFen(item.amount_fen)} · ${item.count} 笔` })) }]),
        { type: 'text', text: bill.anomalies.length
          ? `${bill.anomalies.length} 笔消费符合短时间内同商户同金额的需核对规则；这不代表已确认欺诈。`
          : '未发现符合“同商户、同金额、10 分钟内重复”规则的消费。' },
        ...(bill.anomalies.length ? [{ type: 'list' as const, rows: bill.anomalies.map((item) => ({ label: item.counterparty, value: `${formatCnyFen(item.amount_fen)} · ${billTime(item.previous_occurred_at)} / ${billTime(item.occurred_at)}（北京时间）· ${item.reason}` })) }] : []),
        ...(bill.ignored_count ? [{ type: 'text' as const, text: `${bill.ignored_count} 笔流水因方向未知未计入收支。` }] : []),
      ]
      setCard({ version: 1, id: `bill-${bill.month}-${accountId ?? 'service-selected'}`, title: `${bill.month} 账单`, source: `${bill.account_name} · ${bill.masked_number} · 北京时间自然月 · 账户现金流口径`, observedAt: queryTimestamp(), blocks })
      setCardAccount({ name: bill.account_name, maskedNumber: bill.masked_number })
      setSaved(false)
    } catch (err) {
      const message = queryErrorMessage(err)
      setError(`${message}${card ? '；下方仍为上次成功查询的账单。' : ''}`)
    } finally {
      setLoading(false)
    }
  }

  async function save() {
    if (!card || loading || saving || saved) return
    setSaving(true)
    setError(null)
    try { await saveSnapshot(userId, card); setSaved(true) } catch { setError('保存失败，请检查本地存储后重试。') } finally { setSaving(false) }
  }

  return <section id="asset-section-bill" className="scroll-mt-[68px] border-t border-line pt-5">
    <h3 className="text-sm font-semibold text-ink">月度账单</h3>
    <form onSubmit={(event) => void query(event)} className="mt-3 space-y-3">
      {billAccounts && billAccounts.length > 1 && <div>
        <label htmlFor="bill-account" className="mb-1.5 block text-sm text-ink">账户</label>
        <select id="bill-account" required value={selectedAccount ? selectedAccountId : ''} disabled={loading || saving} onChange={(event) => changeAccount(event.target.value)} className="min-h-11 w-full min-w-0 rounded-xl border border-line bg-white px-3 text-base text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
          <option value="">请选择账户</option>
          {billAccounts.map((account) => <option key={account.account_id} value={account.account_id}>{account.name} · {account.masked_number}</option>)}
        </select>
      </div>}
      {billAccounts?.length === 1 && <p className="truncate text-sm text-ink">账户 · {billAccounts[0].name} · {billAccounts[0].masked_number}</p>}
      {accountListLoading && <p role="status" className="text-xs text-muted">正在读取可供筛选的账户…</p>}
      {noAvailableAccounts && <p role="status" className="text-xs text-muted">{emptyAccountMessage(accounts ?? [])}</p>}
      {accounts === null && !accountListLoading && accountListError && <p role="status" className="text-xs leading-5 text-muted">账户列表暂不可用，仍可尝试查询单账户账单；若有多个账户，请先重试资产加载并选择账户。</p>}
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <label htmlFor="bill-month" className="mb-1.5 block text-sm text-ink">月份 · 北京时间</label>
          <input id="bill-month" type="month" required value={month} disabled={loading || saving} onChange={(event) => { setMonth(event.target.value); resetResult() }} className="min-h-11 w-full min-w-0 rounded-xl border border-line bg-white px-3 text-base text-ink focus-visible:outline-2 focus-visible:outline-jade-700" />
        </div>
        <button type="submit" disabled={queryDisabled} className="min-h-11 shrink-0 rounded-xl bg-jade-700 px-4 text-sm font-medium text-white transition hover:bg-jade-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 disabled:cursor-not-allowed disabled:opacity-50">{loading ? '查询中…' : '查询'}</button>
      </div>
    </form>
    {error && <p role="alert" className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm leading-5 text-red-800">{error}</p>}
    {card && <div className="mt-4">
      {cardAccount && accounts === null && <p className="mb-2 truncate text-xs text-muted">账单账户 · {cardAccount.name} · {cardAccount.maskedNumber}</p>}
      <IntelligentCard value={card} hidden={hidden} />
      <button type="button" disabled={loading || saving || saved} onClick={() => void save()} className="mt-3 min-h-11 rounded-xl border border-line bg-white px-4 text-sm font-medium text-ink transition hover:bg-[#f1f6f4] focus-visible:outline-2 focus-visible:outline-jade-700 disabled:cursor-not-allowed disabled:opacity-60">{saved ? '已收藏到此设备' : saving ? '保存中…' : '收藏快照'}</button>
      <p className="mt-2 text-xs leading-5 text-muted">快照仅保存在此设备；请确认展示内容后再收藏。</p>
    </div>}
  </section>
}
