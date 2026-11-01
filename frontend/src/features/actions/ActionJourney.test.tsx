// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { ActionJourney } from './ActionJourney'
import { PendingActionBanner } from './PendingActionBanner'
import type { StreamEvent } from '@/lib/sse'

afterEach(cleanup)

it('高风险验证按真实阶段推进，验证完成不等于业务已完成', () => {
  const { rerender } = render(<ActionJourney stage="review" needsVerification />)
  expect(screen.getByRole('listitem', { current: 'step' }).textContent).toContain('核对信息')
  expect(screen.getByText(/当前操作尚未执行/)).toBeTruthy()
  rerender(<ActionJourney stage="code" needsVerification />)
  expect(screen.getByRole('listitem', { current: 'step' }).textContent).toContain('模拟验证')
  rerender(<ActionJourney stage="ready" needsVerification />)
  expect(screen.getByRole('listitem', { current: 'step' }).textContent).toContain('执行操作')
  expect(screen.getByText(/银行业务尚未执行/)).toBeTruthy()
  expect(screen.queryByText('服务端已确认完成')).toBeNull()
  rerender(<ActionJourney stage="complete" needsVerification />)
  expect(screen.queryByRole('listitem', { current: 'step' })).toBeNull()
  expect(screen.getByText('服务端已确认完成')).toBeTruthy()
})

it('结果未知不能显示任何已完成阶段，不假装自动重试', () => {
  const { rerender } = render(<ActionJourney stage="unknown" needsVerification />)
  expect(screen.getByText('执行结果尚不确定')).toBeTruthy()
  expect(screen.queryByText('服务端已确认完成')).toBeNull()
  expect(screen.queryByRole('listitem', { current: 'step' })).toBeNull()
  expect(screen.getByText(/请先查询服务端状态/)).toBeTruthy()
  rerender(<ActionJourney stage="recover_execute" needsVerification />)
  expect(screen.getByRole('listitem', { current: 'step' }).textContent).toContain('执行操作')
  expect(screen.getByText(/由你手动决定是否继续/)).toBeTruthy()
  rerender(<ActionJourney stage="cancelled" needsVerification />)
  expect(screen.getByText('操作已终止')).toBeTruthy()
  expect(screen.queryByText('服务端已确认完成')).toBeNull()
})

it('低风险操作用确认而不是验证码，忙碌状态明确禁止重复提交', () => {
  render(<ActionJourney stage="review" needsVerification={false} busy />)
  expect(within(screen.getByRole('list', { name: '操作步骤' })).getByText('确认意向')).toBeTruthy()
  expect(screen.getByText('正在等待服务端响应')).toBeTruthy()
  expect(screen.getByText(/请勿重复操作/)).toBeTruthy()
})

it('待处理操作横幅不暴露金额，且能通过按钮重新打开', () => {
  const onOpen = vi.fn()
  const event = {
    type: 'action_required', confirmation_token: 'ignored', transfer_id: 2,
    action: { id: 9, action_type: 'transfer', risk_level: 'red', status: 'pending', expires_at: '2035-01-01T00:00:00Z',
      details: { account_masked: '****8899', recipient_name: '私密姓名', amount_fen: 887766, currency: 'CNY' } },
  } as Extract<StreamEvent, { type: 'action_required' }>
  render(<PendingActionBanner event={event} onOpen={onOpen} />)
  expect(screen.getByText(/模拟转账/)).toBeTruthy()
  expect(screen.queryByText(/8,877/)).toBeNull()
  expect(screen.queryByText('私密姓名')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '查看待处理操作' }))
  expect(onOpen).toHaveBeenCalledTimes(1)
})
