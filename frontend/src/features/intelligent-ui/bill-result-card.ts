import { billSchema } from './bill-data-schema'
import type { CardDescription } from './schema'
import { formatCnyFen } from '@/lib/format'

/** Accept only a validated successful GREEN monthly-bill tool payload. */
export function billResultCard(input: unknown): CardDescription | null {
  const parsed = billSchema.safeParse(input)
  if (!parsed.success) return null
  const bill = parsed.data
  const blocks: CardDescription['blocks'] = [
    { type: 'group', layout: 'columns', blocks: [
      { type: 'metric', label: '消费', value: bill.consumption_fen, unit: 'CNY_FEN' },
      { type: 'metric', label: '账户总支出', value: bill.expense_fen, unit: 'CNY_FEN' },
    ] },
    { type: 'list', rows: [
      { label: '总收入', value: formatCnyFen(bill.income_fen) },
      { label: '消费笔数', value: `${bill.consumption_count} 笔` },
      { label: '转账转出', value: formatCnyFen(bill.transfer_out_fen) },
      { label: '理财资金转出', value: formatCnyFen(bill.investment_out_fen) },
    ] },
    ...(bill.categories.length === 0
      ? [{ type: 'text' as const, text: '本月没有可统计的消费分类。' }]
      : bill.categories.length <= 12
        ? [{ type: 'bar_chart' as const, title: '消费分类', rows: bill.categories.map(item => ({ label: item.category, value: item.amount_fen })) }]
        : [{ type: 'list' as const, rows: bill.categories.map(item => ({label:item.category,value:formatCnyFen(item.amount_fen)})) }]),
    ...(bill.anomalies.length ? [{ type: 'text' as const, text: `${bill.anomalies.length} 笔交易符合重复消费核对规则，尚不能判定为异常扣费。` }] : []),
    ...(bill.ignored_count ? [{ type: 'text' as const, text: `${bill.ignored_count} 笔方向未知的流水未计入统计。` }] : []),
  ]
  return {
    version: 1,
    id: `tool-monthly-bill-${bill.month}`,
    title: `${bill.month} 消费与收支`,
    source: `银行账单工具 · ${bill.account_name} · ${bill.masked_number} · 北京时间 · 账户现金流`,
    observedAt: new Date().toISOString(),
    blocks,
  }
}
