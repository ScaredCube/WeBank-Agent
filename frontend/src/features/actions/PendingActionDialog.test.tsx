// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PendingActionDialog } from './PendingActionDialog'
import type { ActionTransport } from './transport'
import { ApiError, api } from '@/lib/api'
import type { StreamEvent } from '@/lib/sse'

const action: Extract<StreamEvent, { type: 'action_required' }> = {
  type: 'action_required', confirmation_token: 'test-token', transfer_id: 42,
  action: { id: 3, action_type: 'transfer', risk_level: 'yellow', status: 'pending', expires_at: '2030-01-01T00:00:00Z', details: { account_masked: '****8899', recipient_name: '测试收款人', amount_fen: 1250, currency: 'CNY' } },
}
const wealthSubscribe: Extract<StreamEvent, { type: 'action_required' }> = {
  type: 'action_required', confirmation_token: 'wealth-token', order_id: 21,
  action: {
    id: 8, action_type: 'wealth_subscribe', risk_level: 'red', status: 'pending',
    expires_at: '2030-01-01T00:00:00Z', details: {
      order_type: 'subscribe', product_id: 2, product_name: '稳健理财', product_category: '固收',
      product_risk_level: 'R2', expected_rate_bps: 275, term_days: 90, account_id: 1,
      account_masked: '****5566', amount_fen: 20_000, note: '备用金', currency: 'CNY',
    },
  },
}
const subscriptionCancel: Extract<StreamEvent, { type: 'action_required' }> = {
  type: 'action_required', confirmation_token: 'subscription-token', subscription_id: 31,
  action: {
    id: 12, action_type: 'subscription_cancel', risk_level: 'yellow', status: 'pending',
    expires_at: '2030-01-01T00:00:00Z', details: {
      subscription_id: 31, merchant: '视频会员', amount_fen: 2500, cycle: 'monthly',
      next_charge_date: '2030-01-15', status: 'active',
    },
  },
}

beforeEach(() => vi.restoreAllMocks())
afterEach(cleanup)

describe('待确认动作', () => {
  it.each([
    { account_masked: '', recipient_name: '测试收款人', amount_fen: 1250, currency: 'CNY' },
    { account_masked: '****8899', recipient_name: '  ', amount_fen: 1250, currency: 'CNY' },
    { account_masked: '****8899', recipient_name: '测试收款人', amount_fen: 1250, currency: 'USD' },
  ])('转账核对字段不完整或币种不支持时不能确认', (details) => {
    render(<PendingActionDialog event={{ ...action, action: { ...action.action, details } }} token="auth" onClose={() => {}} />)
    expect((screen.getByRole('button', { name: '确认' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('alert').textContent).toContain('信息不完整')
  })

  it('确认弹窗精确展示大额整数分', () => {
    const large = { ...action, action: { ...action.action, details: { ...action.action.details, amount_fen: Number.MAX_SAFE_INTEGER } } }
    render(<PendingActionDialog event={large} token="auth" onClose={() => {}} />)
    expect(screen.getByText('¥90,071,992,547,409.91')).toBeTruthy()
  })

  it('确认和执行分开，只有执行成功后显示结果', async () => {
    const user = userEvent.setup()
    const step = vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'confirmed', message: '已确认' })
    const execute = vi.spyOn(api, 'executeTransfer').mockResolvedValue({ status: 'completed', message: '模拟转账已完成' })
    render(<PendingActionDialog event={action} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '确认' }))
    expect(step).toHaveBeenCalledTimes(1)
    expect(execute).not.toHaveBeenCalled()
    expect(screen.getByText('已确认，操作尚未执行。')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '执行操作' }))
    expect(execute).toHaveBeenCalledTimes(1)
    expect(screen.getByText('模拟转账已完成')).toBeTruthy()
  })

  it('挂失缺少卡片信息时不允许启动验证', () => {
    const event = { ...action, transfer_id: undefined, action: { ...action.action, action_type: 'card_loss', risk_level: 'red', details: {} } }
    render(<PendingActionDialog event={event} token="auth" onClose={() => {}} />)
    expect((screen.getByRole('button', { name: '开始模拟验证' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('金额隐藏时不能确认转账', () => {
    render(<PendingActionDialog event={action} token="auth" hidden onTogglePrivacy={() => {}} onClose={() => {}} />)
    expect(screen.queryByText('¥12.50')).toBeNull()
    expect((screen.getByRole('button', { name: '确认' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('button', { name: '查看金额' })).toBeTruthy()
  })

  it('不完整的理财动作不能启动模拟验证', () => {
    const event = { ...wealthSubscribe, order_id: undefined }
    render(<PendingActionDialog event={event} token="auth" onClose={() => {}} />)
    expect((screen.getByRole('button', { name: '开始模拟验证' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('alert').textContent).toContain('信息不完整')
  })

  it('旧演示 transport 未连接理财执行接口时不允许进入确认流程', () => {
    const demoTransport: ActionTransport = {
      step: vi.fn().mockResolvedValue({ status: 'pending', message: '' }),
      executeTransfer: vi.fn().mockResolvedValue({ status: 'completed', message: '' }),
      executeCardLoss: vi.fn().mockResolvedValue({ status: 'lost' }),
      action: vi.fn().mockResolvedValue({ status: 'pending' }),
    }
    render(<PendingActionDialog event={wealthSubscribe} transport={demoTransport} onClose={() => {}} />)

    expect((screen.getByRole('button', { name: '开始模拟验证' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('alert').textContent).toContain('当前演示没有连接此业务接口')
    expect(demoTransport.step).not.toHaveBeenCalled()
  })

  it('申购模拟验证通过后自动执行并核对服务端订单结果', async () => {
    const user = userEvent.setup()
    const step = vi.spyOn(api, 'actionStep')
      .mockResolvedValueOnce({ status: 'pending', message: '验证已开始' })
      .mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
    const execute = vi.spyOn(api, 'executeWealthOrder').mockResolvedValue({
      order_id: 21, order_type: 'subscribe', status: 'completed', transaction_id: 55,
      balance_fen: 80_000, holding_fen: 20_000, message: '模拟理财操作已完成。',
    })
    const resolved = vi.fn()
    render(<PendingActionDialog event={wealthSubscribe} token="auth" onClose={() => {}} onResolved={resolved} />)

    expect(screen.getByText('稳健理财')).toBeTruthy()
    expect(screen.getByText('2.75%')).toBeTruthy()
    expect(screen.getByText(/模拟验证码仅用于演示，不是真实银行身份验证/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '验证' }))
    expect(await screen.findByText('模拟理财操作已完成。')).toBeTruthy()

    expect(step).toHaveBeenNthCalledWith(1, 'auth', 8, 'verification/start', { token: 'wealth-token' })
    expect(step).toHaveBeenNthCalledWith(2, 'auth', 8, 'verification/verify', { token: 'wealth-token', code: '123456' })
    expect(execute).toHaveBeenCalledWith('auth', 21)
    expect(screen.getByText('¥800.00')).toBeTruthy()
    expect(resolved).toHaveBeenCalledWith('completed')
  })

  it('赎回使用对应标题和同一理财订单执行接口', async () => {
    const user = userEvent.setup()
    const redeem = {
      ...wealthSubscribe,
      action: { ...wealthSubscribe.action, action_type: 'wealth_redeem', details: { ...wealthSubscribe.action.details, order_type: 'redeem' } },
    }
    vi.spyOn(api, 'actionStep')
      .mockResolvedValueOnce({ status: 'pending', message: '验证已开始' })
      .mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
    const execute = vi.spyOn(api, 'executeWealthOrder').mockResolvedValue({
      order_id: 21, order_type: 'redeem', status: 'completed', transaction_id: 56,
      balance_fen: 120_000, holding_fen: 0, message: '模拟理财操作已完成。',
    })
    render(<PendingActionDialog event={redeem} token="auth" onClose={() => {}} />)

    expect(screen.getByText('确认模拟赎回')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '验证' }))
    expect(await screen.findByText('该产品持仓')).toBeTruthy()
    expect(execute).toHaveBeenCalledWith('auth', 21)
    expect(screen.getByText('¥0.00')).toBeTruthy()
  })

  it('订阅取消使用黄色确认后再执行，不启动模拟验证码', async () => {
    const user = userEvent.setup()
    const step = vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'confirmed', message: '已确认' })
    const execute = vi.spyOn(api, 'executeSubscriptionCancel').mockResolvedValue({
      subscription_id: 31, status: 'cancelled', message: '模拟订阅已取消。',
    })
    const resolved = vi.fn()
    render(<PendingActionDialog event={subscriptionCancel} token="auth" onClose={() => {}} onResolved={resolved} />)

    expect(screen.getByText('视频会员')).toBeTruthy()
    expect(screen.getByText('每月')).toBeTruthy()
    expect(screen.getByText('2030-01-15')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '确认取消' }))
    expect(step).toHaveBeenCalledWith('auth', 12, 'confirm', { token: 'subscription-token' })
    expect(screen.queryByLabelText('模拟验证码')).toBeNull()
    expect(execute).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '执行模拟取消' }))

    expect(execute).toHaveBeenCalledWith('auth', 12, 31)
    expect(screen.getByText('服务端已确认模拟订阅 #31 已取消。')).toBeTruthy()
    expect(resolved).toHaveBeenCalledWith('completed')
  })

  it('理财执行未知时不自动重试，查到已验证后允许用户手动按原订单编号重试', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep')
      .mockResolvedValueOnce({ status: 'pending', message: '验证已开始' })
      .mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
    const execute = vi.spyOn(api, 'executeWealthOrder')
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce({
        order_id: 21, order_type: 'subscribe', status: 'completed', transaction_id: 57,
        balance_fen: 60_000, holding_fen: 40_000, message: '模拟理财操作已完成。',
      })
    const check = vi.spyOn(api, 'action').mockResolvedValue({ status: 'verified' })
    render(<PendingActionDialog event={wealthSubscribe} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '验证' }))
    expect(await screen.findByText(/执行结果暂不确定/)).toBeTruthy()
    expect(execute).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: '查询服务端状态' }))
    expect(check).toHaveBeenCalledWith('auth', 8)
    expect(execute).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/页面不会自动重发/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '按原动作编号重试' }))
    expect(execute).toHaveBeenCalledTimes(2)
    expect(execute).toHaveBeenLastCalledWith('auth', 21)
    expect(screen.getByText('模拟理财操作已完成。')).toBeTruthy()
  })

  it('状态仍为已验证但设备时间已超过有效期时，不提供重试', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep')
      .mockResolvedValueOnce({ status: 'pending', message: '验证已开始' })
      .mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
    vi.spyOn(api, 'executeWealthOrder').mockRejectedValueOnce(new TypeError('network'))
    vi.spyOn(api, 'action').mockResolvedValue({ status: 'verified' })
    const event = { ...wealthSubscribe, action: { ...wealthSubscribe.action, expires_at: '2020-01-01T00:00:00Z' } }
    render(<PendingActionDialog event={event} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '验证' }))
    await user.click(await screen.findByRole('button', { name: '查询服务端状态' }))
    expect(screen.getByText(/按本设备时间，此操作可能已过有效期/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: '按原动作编号重试' })).toBeNull()
  })

  it('订阅执行未知时只在服务端仍为已确认后提供同一动作的手动重试', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'confirmed', message: '已确认' })
    const execute = vi.spyOn(api, 'executeSubscriptionCancel')
      .mockRejectedValueOnce(new TypeError('network'))
      .mockResolvedValueOnce({ subscription_id: 31, status: 'cancelled', message: '模拟订阅已取消。' })
    const check = vi.spyOn(api, 'action').mockResolvedValue({ status: 'confirmed' })
    render(<PendingActionDialog event={subscriptionCancel} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '确认取消' }))
    await user.click(screen.getByRole('button', { name: '执行模拟取消' }))
    expect(execute).toHaveBeenCalledTimes(1)
    expect(screen.getByText(/请求结果暂不确定/)).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '查询服务端状态' }))
    expect(check).toHaveBeenCalledWith('auth', 12)
    expect(execute).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '按原动作编号重试' }))
    expect(execute).toHaveBeenCalledTimes(2)
    expect(execute).toHaveBeenLastCalledWith('auth', 12, 31)
  })

  it('确认响应状态异常时不开放执行', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'pending', message: '未确认' })
    render(<PendingActionDialog event={action} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '确认' }))
    expect(screen.queryByRole('button', { name: '执行操作' })).toBeNull()
    expect(screen.getByText(/请求结果暂不确定/)).toBeTruthy()
  })

  it('确认请求断线后可查询状态并取消仍待确认的动作', async () => {
    const user = userEvent.setup()
    const step = vi.spyOn(api, 'actionStep').mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce({ status: 'cancelled', message: '已取消' })
    vi.spyOn(api, 'action').mockResolvedValue({ status: 'pending' })
    render(<PendingActionDialog event={action} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '确认' }))
    expect(screen.getByText(/请求结果暂不确定/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '查询服务端状态' }))
    await user.click(screen.getByRole('button', { name: '取消操作' }))
    await waitFor(() => expect(screen.getByText('已取消')).toBeTruthy())
    expect(step).toHaveBeenCalledTimes(2)
  })

  it('红色挂失通过模拟验证后自动执行', async () => {
    const user = userEvent.setup()
    const red = { ...action, transfer_id: undefined, action: { ...action.action, action_type: 'card_loss', risk_level: 'red', details: { card_id: 2, masked_number: '****1234', account_name: '测试账户' } } }
    const step = vi.spyOn(api, 'actionStep').mockResolvedValueOnce({ status: 'pending', message: '验证已开始' }).mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
    const execute = vi.spyOn(api, 'executeCardLoss').mockResolvedValue({ status: 'lost' })
    const resolved = vi.fn()
    render(<PendingActionDialog event={red} token="auth" onClose={() => {}} onResolved={resolved} />)
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '123456')
    await user.click(screen.getByRole('button', { name: '验证' }))
    expect(await screen.findByText('模拟卡片已挂失。')).toBeTruthy()
    expect(execute).toHaveBeenCalledTimes(1)
    expect(step).toHaveBeenCalledTimes(2)
    expect(resolved).toHaveBeenCalledWith('completed')
  })

  it('移除本地记录不会被误认为服务端动作已解决', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep').mockRejectedValue(new TypeError('network'))
    const resolved = vi.fn()
    render(<PendingActionDialog event={action} token="auth" onClose={() => {}} onResolved={resolved} />)
    await user.click(screen.getByRole('button', { name: '确认' }))
    await user.click(await screen.findByRole('button', { name: '移除本地记录' }))
    expect(resolved).not.toHaveBeenCalled()
  })

  it('验证阶段取消被拒绝时提供状态核实入口', async () => {
    const user = userEvent.setup()
    const red = { ...action, transfer_id: undefined, action: { ...action.action, action_type: 'card_loss', risk_level: 'red', details: { card_id: 2, masked_number: '****1234' } } }
    vi.spyOn(api, 'actionStep').mockResolvedValueOnce({ status: 'pending', message: '验证已开始' }).mockRejectedValueOnce(new ApiError('取消失败：动作无效、已处理或已过期', 400))
    vi.spyOn(api, 'action').mockResolvedValue({ status: 'expired' })
    const resolved = vi.fn()
    render(<PendingActionDialog event={red} token="auth" onClose={() => {}} onResolved={resolved} />)
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.click(screen.getByRole('button', { name: '取消操作' }))
    await user.click(await screen.findByRole('button', { name: '查询服务端状态' }))
    expect(await screen.findByText(/服务端状态：已过期/)).toBeTruthy()
    expect(resolved).toHaveBeenCalledWith('expired')
  })

  it('验证码被拒绝后仍允许用户修改验证码', async () => {
    const user = userEvent.setup()
    const red = { ...action, transfer_id: undefined, action: { ...action.action, action_type: 'card_loss', risk_level: 'red', details: { card_id: 2, masked_number: '****1234' } } }
    vi.spyOn(api, 'actionStep').mockResolvedValueOnce({ status: 'pending', message: '验证已开始' }).mockRejectedValueOnce(new ApiError('验证码错误或已锁定', 400))
    render(<PendingActionDialog event={red} token="auth" onClose={() => {}} />)
    await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
    await user.type(screen.getByLabelText('模拟验证码'), '000000')
    await user.click(screen.getByRole('button', { name: '验证' }))
    expect(await screen.findByText('验证码错误或已锁定')).toBeTruthy()
    expect(screen.getByLabelText('模拟验证码')).toBeTruthy()
    expect(screen.getByRole('button', { name: '取消操作' })).toBeTruthy()
  })

  it('执行时断线不会自动重试，查询完成状态后才显示已完成', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'confirmed', message: '已确认' })
    const execute = vi.spyOn(api, 'executeTransfer').mockRejectedValue(new TypeError('network'))
    vi.spyOn(api, 'action').mockResolvedValue({ status: 'completed' })
    const resolved = vi.fn()
    render(<PendingActionDialog event={action} token="auth" onClose={() => {}} onResolved={resolved} />)
    await user.click(screen.getByRole('button', { name: '确认' }))
    await user.click(screen.getByRole('button', { name: '执行操作' }))
    expect(screen.getByText(/请求结果暂不确定/)).toBeTruthy()
    expect(execute).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '查询服务端状态' }))
    expect(screen.getByText(/服务端状态：已完成/)).toBeTruthy()
    expect(execute).toHaveBeenCalledTimes(1)
    expect(resolved).toHaveBeenCalledWith('completed')
  })
})
