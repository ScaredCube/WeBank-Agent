// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CardLossButton } from './CardLossButton'
import { ApiError, api } from '@/lib/api'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('准备成功后交给固定的模拟验证流程', async () => {
  const user = userEvent.setup()
  const prepare = vi.spyOn(api, 'prepareCardLoss').mockResolvedValue({ action_id: 3, confirmation_token: 'test-token' })
  vi.spyOn(api, 'actionDetails').mockResolvedValue({ id: 3, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const prepared = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={prepared} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  expect(prepared).toHaveBeenCalledWith(expect.objectContaining({ type: 'action_required', action: expect.objectContaining({ id: 3 }) }))
  expect(prepare).toHaveBeenCalledWith('test', 2, expect.stringMatching(/^[A-Za-z0-9_-]{16,64}$/))
})

it('准备响应丢失后不自动重试；同键核对出待处理申请时只允许取消', async () => {
  const user = userEvent.setup()
  const prepare = vi.spyOn(api, 'prepareCardLoss')
    .mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValueOnce({ action_id: 3, confirmation_token: null })
  vi.spyOn(api, 'actionDetails').mockResolvedValue({ id: 3, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const cancel = vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'cancelled', message: '已取消，操作未执行。' })
  const resolved = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={() => {}} onResolved={resolved} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  expect((await screen.findByRole('alert')).textContent).toContain('结果暂不确定')
  expect(prepare).toHaveBeenCalledTimes(1)

  await user.click(screen.getByRole('button', { name: '核对准备结果' }))
  expect(await screen.findByText(/一次性验证凭证无法恢复/)).toBeTruthy()
  const key = prepare.mock.calls[0][2]
  expect(prepare).toHaveBeenCalledTimes(2)
  expect(prepare.mock.calls[1][2]).toBe(key)
  expect(screen.queryByRole('button', { name: '确认挂失' })).toBeNull()
  expect(screen.queryByRole('button', { name: '执行操作' })).toBeNull()

  await user.click(screen.getByRole('button', { name: '取消待处理申请' }))
  expect(await screen.findByText(/挂失申请已取消，操作未执行/)).toBeTruthy()
  expect(cancel).toHaveBeenCalledWith('test', 3, 'cancel')
  expect(resolved).toHaveBeenCalledWith(2, 'cancelled')
})

it('同键核对发现后端尚未创建申请时，正常取得令牌并进入确认流程', async () => {
  const user = userEvent.setup()
  const prepare = vi.spyOn(api, 'prepareCardLoss')
    .mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValueOnce({ action_id: 4, confirmation_token: 'fresh-test-token' })
  vi.spyOn(api, 'actionDetails').mockResolvedValue({ id: 4, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const prepared = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={prepared} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '核对准备结果' }))
  expect(prepared).toHaveBeenCalledWith(expect.objectContaining({ type: 'action_required', action: expect.objectContaining({ id: 4 }), confirmation_token: 'fresh-test-token' }))
  expect(prepare).toHaveBeenCalledTimes(2)
  expect(prepare.mock.calls[1][2]).toBe(prepare.mock.calls[0][2])
})

it('同键核对失败时保留状态，不解除待核实标记', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'prepareCardLoss').mockRejectedValueOnce(new TypeError('network')).mockRejectedValueOnce(new ApiError('请求受限', 429))
  const recoveryChange = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={() => {}} onRecoveryChange={recoveryChange} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '核对准备结果' }))
  expect((await screen.findByRole('alert')).textContent).toContain('请求受限')
  expect(screen.getByRole('button', { name: '核对准备结果' })).toBeTruthy()
  expect(recoveryChange).toHaveBeenLastCalledWith(2, expect.objectContaining({ status: 'unknown' }))
})

it('已找回动作编号但状态查询失败时保留编号并只重试只读查询', async () => {
  const user = userEvent.setup()
  const prepare = vi.spyOn(api, 'prepareCardLoss')
    .mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValueOnce({ action_id: 8, confirmation_token: null })
  const actionDetails = vi.spyOn(api, 'actionDetails')
    .mockRejectedValueOnce(new TypeError('status network'))
    .mockResolvedValueOnce({ id: 8, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const recoveryChange = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={() => {}} onRecoveryChange={recoveryChange} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '核对准备结果' }))
  expect(await screen.findByText(/已取得申请编号，但暂时无法读取其状态/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '核对申请状态' })).toBeTruthy()

  await user.click(screen.getByRole('button', { name: '核对申请状态' }))
  expect(await screen.findByText(/一次性验证凭证无法恢复/)).toBeTruthy()
  expect(prepare).toHaveBeenCalledTimes(2)
  expect(prepare.mock.calls[1][2]).toBe(prepare.mock.calls[0][2])
  expect(actionDetails).toHaveBeenCalledTimes(2)
  expect(screen.getByRole('button', { name: '取消待处理申请' })).toBeTruthy()
})

it('状态已确认但凭证缺失时只显示状态查询，不提供确认、验证或执行入口', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'prepareCardLoss').mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce({ action_id: 5, confirmation_token: null })
  vi.spyOn(api, 'actionDetails').mockResolvedValue({ id: 5, action_type: 'card_loss', status: 'confirmed', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const prepared = vi.fn()
  const cancel = vi.spyOn(api, 'actionStep')
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={prepared} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '核对准备结果' }))

  expect(await screen.findByText(/申请已确认，但一次性凭证无法恢复/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '核对申请状态' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: '取消待处理申请' })).toBeNull()
  expect(prepared).not.toHaveBeenCalled()
  expect(cancel).not.toHaveBeenCalled()
})

it('动作终态会清除恢复状态并刷新银行卡', async () => {
  const user = userEvent.setup()
  const prepare = vi.spyOn(api, 'prepareCardLoss')
    .mockRejectedValueOnce(new TypeError('network'))
    .mockResolvedValueOnce({ action_id: 6, confirmation_token: null })
    .mockResolvedValueOnce({ action_id: 7, confirmation_token: 'new-operation-token' })
  vi.spyOn(api, 'actionDetails')
    .mockResolvedValueOnce({ id: 6, action_type: 'card_loss', status: 'expired', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
    .mockResolvedValueOnce({ id: 7, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  const resolved = vi.fn()
  const recoveryChange = vi.fn()
  const prepared = vi.fn()
  render(<CardLossButton token="test" cardId={2} disabled={false} onBusyChange={() => {}} onPrepared={prepared} onRecoveryChange={recoveryChange} onResolved={resolved} />)
  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '核对准备结果' }))

  expect(await screen.findByText(/挂失申请已过期/)).toBeTruthy()
  expect(recoveryChange).toHaveBeenLastCalledWith(2, null)
  expect(resolved).toHaveBeenCalledWith(2, 'expired')
  expect(screen.getByRole('button', { name: '模拟挂失' })).toBeTruthy()

  await user.click(screen.getByRole('button', { name: '模拟挂失' }))
  expect(prepare).toHaveBeenCalledTimes(3)
  expect(prepare.mock.calls[2][2]).not.toBe(prepare.mock.calls[0][2])
  expect(prepared).toHaveBeenCalledWith(expect.objectContaining({ action: expect.objectContaining({ id: 7 }) }))
})
