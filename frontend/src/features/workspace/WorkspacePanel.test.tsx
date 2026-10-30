// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WorkspacePanel } from './WorkspacePanel'
import { api } from '@/lib/api'
import type { AuditEntry } from '@/lib/api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('账户和银行卡分开展示；银行卡操作不依赖名称或脱敏尾号匹配', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'bankDashboard').mockResolvedValue({
    accounts: [{ account_id: 1, name: '日常账户', masked_number: '****8899', currency: 'CNY', balance_fen: 12345, status: 'active', card_status: 'active', can_transfer: true }],
    contacts: [],
    holdings: [],
    risk_profile: { risk_level: 'R2', score: 60, assessed_at: null },
    generated_at: '2026-01-01T00:00:00Z',
  })
  vi.spyOn(api, 'cards').mockResolvedValue([{ card_id: 7, account_name: '不同的显示名称', masked_number: '****0007', status: 'active', account_status: 'active' }])
  const { rerender } = render(<WorkspacePanel panel="assets" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  expect(await screen.findByText('日常账户')).toBeTruthy()
  expect(await screen.findByText('不同的显示名称')).toBeTruthy()
  expect(screen.getByText(/银行卡 · \*\*\*\*0007/)).toBeTruthy()
  await user.click(screen.getByText('卡片操作'))
  expect(await screen.findByRole('button', { name: '模拟挂失' })).toBeTruthy()
  expect(screen.getByText('¥123.45')).toBeTruthy()
  rerender(<WorkspacePanel panel="assets" token="test" userId={1} hidden onClose={() => {}} onTogglePrivacy={() => {}} />)
  expect(screen.getByText('日常账户')).toBeTruthy()
  expect(screen.getByText(/\*\*\*\*8899 · CNY/)).toBeTruthy()
  expect(screen.getByText('不同的显示名称')).toBeTruthy()
  expect(screen.queryByText('¥123.45')).toBeNull()
  expect(screen.getByText('••••••')).toBeTruthy()
})

it('银行卡加载失败时仍能查询账单', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'cards').mockRejectedValue(new Error('银行卡暂不可用'))
  vi.spyOn(api, 'bankDashboard').mockResolvedValue({
    accounts: [{ account_id: 3, name: '日常账户', masked_number: '****0003', currency: 'CNY', balance_fen: 1000, status: 'active', card_status: 'missing', can_transfer: false }],
    contacts: [],
    holdings: [],
    risk_profile: { risk_level: 'R2', score: 60, assessed_at: null },
    generated_at: '2026-01-01T00:00:00Z',
  })
  const bill = vi.spyOn(api, 'monthlyBill').mockResolvedValue({ month: '2026-01', account_name: '测试账户', masked_number: '****1234', currency: 'CNY', income_fen: 500, expense_fen: 200, consumption_fen: 200, consumption_count: 1, transfer_out_fen: 0, transfer_out_count: 0, transfer_in_fen: 0, transfer_in_count: 0, investment_out_fen: 0, investment_out_count: 0, investment_in_fen: 0, investment_in_count: 0, categories: [], anomalies: [], ignored_count: 0 })
  render(<WorkspacePanel panel="assets" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  await screen.findByText('银行卡暂不可用')
  await user.click(screen.getByRole('button', { name: '查询' }))
  expect(await screen.findByText('2026-01 账单')).toBeTruthy()
  expect(bill).toHaveBeenCalledWith('test', expect.stringMatching(/^\d{4}-\d{2}$/), 3)
})

it('刷新后忽略之前尚未完成的分页结果', async () => {
  const user = userEvent.setup()
  const entry = (id: number, event_type: string): AuditEntry => ({ id, event_type, result: 'success', created_at: '2026-01-01T00:00:00Z', action_id: null })
  let finishPage!: (entries: AuditEntry[]) => void
  const page = new Promise<AuditEntry[]>((resolve) => { finishPage = resolve })
  vi.spyOn(api, 'audit')
    .mockResolvedValueOnce(Array.from({ length: 50 }, (_, index) => entry(index + 1, 'tool_called')))
    .mockReturnValueOnce(page)
    .mockResolvedValueOnce([entry(100, 'risk_assessed')])
  render(<WorkspacePanel panel="activity" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  await screen.findByRole('button', { name: '加载更多' })
  await user.click(screen.getByRole('button', { name: '加载更多' }))
  await user.click(screen.getByRole('button', { name: '刷新' }))
  await screen.findByText('风险检查')
  await act(async () => { finishPage([entry(51, 'action_confirmed')]); await page })
  expect(screen.queryByText('确认操作')).toBeNull()
  expect(screen.getByText('风险检查')).toBeTruthy()
})

it('加载更多失败时保留已有记录并允许重试', async () => {
  const user = userEvent.setup()
  const entries: AuditEntry[] = Array.from({ length: 50 }, (_, index) => ({ id: index + 1, event_type: 'tool_called', result: 'success', created_at: '2026-01-01T00:00:00Z', action_id: null }))
  vi.spyOn(api, 'audit').mockResolvedValueOnce(entries).mockRejectedValueOnce(new Error('分页暂不可用'))
  render(<WorkspacePanel panel="activity" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  await user.click(await screen.findByRole('button', { name: '加载更多' }))
  expect((await screen.findByRole('alert')).textContent).toContain('分页暂不可用')
  expect(screen.getAllByText('工具调用')).toHaveLength(50)
  expect(screen.getByRole('button', { name: '加载更多' })).toBeTruthy()
})

it('操作记录区分写操作和查询，并展示可用的关联信息', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'audit').mockResolvedValue([{ id: 1, event_type: 'tool_called', tool: 'prepare_transfer', result: 'failed', created_at: '2026-01-01T00:00:00Z', action_id: 8, conversation_id: 4, transfer_id: 12 }])
  render(<WorkspacePanel panel="activity" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  expect(await screen.findByText('准备转账')).toBeTruthy()
  expect(screen.getByText('失败')).toBeTruthy()
  expect(screen.queryByText('发起查询')).toBeNull()
  await user.click(screen.getByText('准备转账'))
  expect(screen.getByText('会话 #4')).toBeTruthy()
  expect(screen.getByText('动作 #8')).toBeTruthy()
  expect(screen.getByText('转账 #12')).toBeTruthy()
})

it('未知记录使用中性名称和状态，不暴露内部枚举', async () => {
  vi.spyOn(api, 'audit').mockResolvedValue([{ id: 1, event_type: 'future_event', result: 'future_result', created_at: '2026-01-01T00:00:00Z', action_id: null }])
  render(<WorkspacePanel panel="activity" token="test" userId={1} hidden={false} onClose={() => {}} onTogglePrivacy={() => {}} />)
  expect(await screen.findByText('操作记录', { selector: 'span' })).toBeTruthy()
  expect(screen.getByText('状态未知')).toBeTruthy()
  expect(screen.queryByText('future_result')).toBeNull()
})
