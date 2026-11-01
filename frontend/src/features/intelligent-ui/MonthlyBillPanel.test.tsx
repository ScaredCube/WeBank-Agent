// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { MonthlyBillPanel } from './MonthlyBillPanel'
import { api } from '@/lib/api'
import type { BankAccountOverview } from '@/lib/api'
import * as store from '@/features/collections/store'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const bill = (month: string, accountName = '测试账户') => ({
  month,
  account_name: accountName,
  masked_number: '****1234',
  currency: 'CNY',
  income_fen: 0,
  expense_fen: 2000,
  consumption_fen: 2000,
  consumption_count: 2,
  transfer_out_fen: 0,
  transfer_out_count: 0,
  transfer_in_fen: 0,
  transfer_in_count: 0,
  investment_out_fen: 0,
  investment_out_count: 0,
  investment_in_fen: 0,
  investment_in_count: 0,
  categories: [],
  ignored_count: 0,
  anomalies: [],
})

const account = (account_id: number, name: string, overrides: Partial<BankAccountOverview> = {}): BankAccountOverview => ({
  account_id,
  name,
  masked_number: `****${account_id}`,
  currency: 'CNY',
  balance_fen: 1000,
  status: 'active',
  card_status: 'active',
  can_transfer: true,
  ...overrides,
})

it('查询失败时保留同一查询条件下上次成功的账单', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValueOnce(bill('2026-01')).mockRejectedValueOnce(new Error('查询暂不可用'))
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('2026-01 账单')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect((await screen.findByRole('alert')).textContent).toContain('查询暂不可用')
  expect(screen.getByText('2026-01 账单')).toBeTruthy()
})

it('多账户时必须选择账户，并以账户 ID 查询；切换账户会清除旧结果', async () => {
  const user = userEvent.setup()
  const request = vi.spyOn(api, 'monthlyBill').mockResolvedValueOnce(bill('2026-01', '账户一')).mockResolvedValueOnce(bill('2026-01', '账户二'))
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} accounts={[
    account(7, '账户一'),
    account(9, '账户二'),
    account(11, '冻结账户', { status: 'frozen' }),
    account(13, '外币账户', { currency: 'USD' }),
  ]} />)
  const query = screen.getByRole('button', { name: '查询' }) as HTMLButtonElement
  expect(query.disabled).toBe(true)
  expect(screen.getByLabelText('账户').querySelectorAll('option')).toHaveLength(3)
  await user.selectOptions(screen.getByLabelText('账户'), '7')
  await user.click(query)
  expect(await screen.findByText('2026-01 账单')).toBeTruthy()
  expect(request).toHaveBeenLastCalledWith('test', expect.stringMatching(/^\d{4}-\d{2}$/), 7)

  await user.selectOptions(screen.getByLabelText('账户'), '9')
  expect(screen.queryByText('2026-01 账单')).toBeNull()
  await user.click(query)
  expect(await screen.findByText('2026-01 账单')).toBeTruthy()
  expect(request).toHaveBeenLastCalledWith('test', expect.stringMatching(/^\d{4}-\d{2}$/), 9)
})

it('账户列表加载失败时保留服务端的单账户回退，并解释多账户错误', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockRejectedValue(new Error('请指定要查询的账户'))
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} accounts={null} accountListError="账户数据暂不可用" />)
  expect(screen.getByText(/仍可尝试查询单账户账单/)).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText(/当前有多个可用账户/)).toBeTruthy()
})

it('查询月份发生变化时不保留上一月的结果', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue(bill('2026-01'))
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('2026-01 账单')).toBeTruthy()
  await user.clear(screen.getByLabelText(/月份/))
  await user.type(screen.getByLabelText(/月份/), '2026-02')
  expect(screen.queryByText('2026-01 账单')).toBeNull()
})

it('收藏尚未完成时不能发起新查询，保存结果只对应当前账单', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValueOnce(bill('2026-01')).mockResolvedValueOnce(bill('2026-02'))
  let complete!: () => void
  const pending = new Promise<void>((resolve) => { complete = resolve })
  vi.spyOn(store, 'saveSnapshot').mockImplementation(async () => { await pending; return { id: 'snapshot', savedAt: '', card: {} } })
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  await user.click(await screen.findByRole('button', { name: '收藏快照' }))
  expect((screen.getByRole('button', { name: '查询' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByLabelText(/月份/) as HTMLInputElement).disabled).toBe(true)
  await act(async () => { complete(); await pending })
  expect(await screen.findByRole('button', { name: '已收藏到此设备' })).toBeTruthy()
  expect((screen.getByRole('button', { name: '查询' }) as HTMLButtonElement).disabled).toBe(false)
  await user.clear(screen.getByLabelText(/月份/))
  await user.type(screen.getByLabelText(/月份/), '2026-02')
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('2026-02 账单')).toBeTruthy()
  expect((screen.getByRole('button', { name: '收藏快照' }) as HTMLButtonElement).disabled).toBe(false)
})

it('错误的账单金额不会被展示或收藏', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue({ ...bill('2026-01'), expense_fen: '1000' })
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByRole('alert')).toBeTruthy()
  expect(screen.queryByRole('button', { name: '收藏快照' })).toBeNull()
})

it('可核对重复消费的商户、金额和两次时间，并说明检测规则及欺诈边界', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue({ ...bill('2026-01'), anomalies: [{ status: '需核对', reason: '同一商户同金额消费在10分钟内重复', counterparty: '测试商户', amount_fen: 1000, occurred_at: '2026-01-05T10:05:00+08:00', previous_occurred_at: '2026-01-05T10:00:00+08:00' }] })
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('测试商户')).toBeTruthy()
  expect(screen.getByText(/¥10\.00/)).toBeTruthy()
  expect(screen.getByText(/10:00/)).toBeTruthy()
  expect(screen.getByText(/10:05/)).toBeTruthy()
  expect(screen.getByText(/不代表已确认欺诈/)).toBeTruthy()
})

it('消费分类显示笔数；隐私模式隐藏金额但保留账单账户身份', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue({ ...bill('2026-01'), categories: [{ category: '餐饮', amount_fen: 2000, count: 2 }] })
  const view = render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('消费分类')).toBeTruthy()
  expect(screen.getByText('餐饮 · 2 笔')).toBeTruthy()
  expect(screen.getByTestId('chart-bar')).toBeTruthy()
  view.rerender(<MonthlyBillPanel token="test" userId={1} hidden accounts={[account(1, '测试账户')]} />)
  expect(screen.getByLabelText('图表数值已隐藏')).toBeTruthy()
  expect(screen.getByText(/账户 · 测试账户/)).toBeTruthy()
  expect(screen.queryByTestId('chart-bar')).toBeNull()
  expect(screen.queryByText('¥20.00')).toBeNull()
})

it('收藏来源保存服务端脱敏账户身份，隐私模式隐藏来源但保留查询对象身份', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue(bill('2026-01'))
  const save = vi.spyOn(store, 'saveSnapshot').mockResolvedValue({ id: 'snapshot', savedAt: '', card: {} })
  const view = render(<MonthlyBillPanel token="test" userId={1} hidden={false} accounts={[account(1234, '测试账户')]} />)
  const source = '测试账户 · ****1234 · 北京时间自然月 · 账户现金流口径'
  const sourceLabel = /测试账户 · \*\*\*\*1234 · 北京时间自然月 · 账户现金流口径/

  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText(sourceLabel)).toBeTruthy()
  await user.click(await screen.findByRole('button', { name: '收藏快照' }))
  expect(save).toHaveBeenCalledWith(1, expect.objectContaining({ source }), undefined, undefined, { kind: 'monthly_bill', month: expect.stringMatching(/^[0-9]{4}-[0-9]{2}$/), accountId: 1234 })

  view.rerender(<MonthlyBillPanel token="test" userId={1} hidden accounts={[account(1234, '测试账户')]} />)
  expect(screen.queryByText(sourceLabel)).toBeNull()
  expect(screen.getByText(/账户 · 测试账户 · \*\*\*\*1234/)).toBeTruthy()
  expect(screen.queryByText('¥20.00')).toBeNull()
})

it('分类超过图表容量时完整展示列表', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'monthlyBill').mockResolvedValue({ ...bill('2026-01'), categories: Array.from({ length: 13 }, (_, i) => ({ category: `分类${i + 1}`, amount_fen: 100, count: 1 })) })
  render(<MonthlyBillPanel token="test" userId={1} hidden={false} />)
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('分类13')).toBeTruthy()
  expect(screen.queryByTestId('chart-bar')).toBeNull()
})
