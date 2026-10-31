import { expect, it } from 'vitest'
import { billResultCard } from './bill-result-card'
import { cardSchema } from './schema'

const sample = {
  month: '2026-10', account_name: '日常账户', masked_number: '****8899', currency: 'CNY',
  income_fen: 600000, expense_fen: 238600, consumption_fen: 145000, consumption_count: 10,
  transfer_out_fen: 40000, transfer_out_count: 1, transfer_in_fen: 0, transfer_in_count: 0,
  investment_out_fen: 53600, investment_out_count: 1, investment_in_fen: 0, investment_in_count: 0,
  categories: [{ category: '餐饮', amount_fen: 90000, count: 6 }, {category:'交通',amount_fen:55000,count:4}],
  anomalies: [], ignored_count: 0,
}

it('真实月度账单构造成通过 schema 的可信结果卡', () => {
  const card = billResultCard(sample)
  expect(cardSchema.safeParse(card).success).toBe(true)
  expect(card?.title).toContain('2026-10')
  expect(card?.source).toContain('银行账单工具')
  const json = JSON.stringify(card)
  expect(json).toContain('145000')
  expect(json).toContain('餐饮')
  expect(json).toContain('账户总支出')
})

it('非法金额或字段缺失时不会生成金融结果卡', () => {
  expect(billResultCard({...sample,consumption_fen:-1})).toBeNull()
  expect(billResultCard({...sample,masked_number:undefined})).toBeNull()
  expect(billResultCard({...sample,categories:[{category:'X',amount_fen:NaN,count:2}]})).toBeNull()
})
