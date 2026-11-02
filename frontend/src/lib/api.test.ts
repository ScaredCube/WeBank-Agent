import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

function respond(value: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(value), { status: 200 })))
}

describe('业务列表响应校验', () => {
  it('历史消息保留服务端的视图与订阅快照', async () => {
    const view = { view_id: 'view-12345678', revision: 3 }
    respond([{ id: 4, role: 'assistant', content: '分析完成', created_at: '2026-11-01T00:00:00Z',
      ui_view: view, subscription_results: { kind: 'subscriptions', data: [] } }])

    const [message] = await api.messages('test', 1)

    expect(message.ui_view).toEqual(view)
    expect(message.subscription_results).toEqual({ kind: 'subscriptions', data: [] })
  })

  it('读取指定视图版本，并以服务端交互端点保存筛选', async () => {
    const responseView = { view_id: 'view-12345678', revision: 4 }
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(responseView), { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)

    await api.view('test-token', 'view-12345678', 2)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/views/view-12345678?revision=2', expect.objectContaining({
      headers: expect.any(Headers),
    }))
    await api.viewInteraction('test-token', 'view-12345678', 3, 'select_category', 'food')
    const [url, init] = fetchMock.mock.calls[1]
    expect(url).toBe('/api/views/view-12345678/interactions')
    expect(init).toMatchObject({ method: 'POST', headers: expect.any(Headers) })
    expect(JSON.parse(init.body)).toMatchObject({
      base_revision: 3, action: 'select_category', value: 'food',
    })
    expect(JSON.parse(init.body).event_id).toMatch(/^[A-Za-z0-9_-]{8,80}$/)
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer test-token')
  })

  it('月账单可指定账户，也保留不指定账户的查询', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    await api.monthlyBill('test', '2026-01', 42)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/bills/monthly?month=2026-01&account_id=42', expect.anything())
    await api.monthlyBill('test')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/bills/monthly', expect.anything())
  })
  it('接受银行卡与审计接口的有效数据', async () => {
    respond([{ card_id: 2, account_id: 1, account_name: '示例账户', masked_number: '****1234', status: 'active', account_status: 'active' }])
    expect(await api.cards('test')).toHaveLength(1)
    respond([{ id: 1, event_type: 'tool_called', result: null, created_at: '2026-01-01T00:00:00Z', action_id: null }])
    expect(await api.audit('test')).toHaveLength(1)
  })

  it('拒绝非数组或错误的银行卡标识', async () => {
    respond({ cards: [] })
    await expect(api.cards('test')).rejects.toThrow('银行卡数据格式异常')
    respond([{ card_id: '2', account_name: '示例账户', masked_number: '****1234', status: 'active', account_status: 'active' }])
    await expect(api.cards('test')).rejects.toThrow('银行卡数据格式异常')
  })

  it('挂失准备携带请求幂等键，并接受首次凭证已不可恢复的响应', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ action_id: 3, confirmation_token: null }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const key = 'card_loss_test_key_0001'
    await expect(api.prepareCardLoss('test-token', 2, key)).resolves.toEqual({ action_id: 3, confirmation_token: null })
    expect(fetchMock).toHaveBeenCalledWith('/api/cards/2/loss/prepare', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ idempotency_key: key }),
      headers: expect.any(Headers),
    }))
  })

  it('拒绝非法记录时间与关联标识', async () => {
    respond([{ id: 1, event_type: 'tool_called', result: null, created_at: '不是时间', action_id: null }])
    await expect(api.audit('test')).rejects.toThrow('操作记录数据格式异常')
    respond([{ id: 1, event_type: 'tool_called', result: null, created_at: '2026-01-01T00:00:00Z', action_id: '3' }])
    await expect(api.audit('test')).rejects.toThrow('操作记录数据格式异常')
  })

  it('损坏的历史消息局部降级，并保留其他消息', async () => {
    respond([{ id: 1, role: 'user', content: '正常消息', created_at: '2026-01-01T00:00:00Z' }, null, { id: 2, role: 'unknown', content: '不可信内容', created_at: '2026-01-01T00:00:00Z' }])
    const messages = await api.messages('test', 1)
    expect(messages[0].content).toBe('正常消息')
    expect(messages[1].unavailable).toBe(true)
    expect(messages[2].unavailable).toBe(true)
    expect(messages[1].id).not.toBe(messages[2].id)
    expect(JSON.stringify(messages)).not.toContain('不可信内容')
  })

  it('拒绝非数组的历史响应', async () => {
    respond({ messages: [] })
    await expect(api.messages('test', 1)).rejects.toThrow('历史消息数据格式异常')
  })
})

describe('动作状态与理财、订阅执行响应', () => {
  it('读取并校验服务端动作状态', async () => {
    respond({
      id: 9, action_type: 'wealth_subscribe', status: 'verified',
      expires_at: '2030-01-01T00:00:00Z', details: {}, risk_level: 'red',
    })
    await expect(api.action('test-token', 9)).resolves.toEqual({ status: 'verified' })

    respond({
      id: 10, action_type: 'wealth_subscribe', status: 'invented',
      expires_at: '2030-01-01T00:00:00Z', details: {}, risk_level: 'red',
    })
    await expect(api.action('test-token', 9)).rejects.toThrow('操作状态数据格式异常')
  })

  it('按原理财订单编号执行并核对订单类型和服务端结果', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      order_id: 21, order_type: 'subscribe', status: 'completed', transaction_id: 55,
      balance_fen: 90_000, holding_fen: 10_000, message: '模拟理财操作已完成。',
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.executeWealthOrder('test-token', 21)).resolves.toMatchObject({
      order_id: 21, order_type: 'subscribe', status: 'completed', transaction_id: 55,
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/wealth/orders/21/execute', expect.objectContaining({
      method: 'POST', headers: expect.any(Headers),
    }))
    expect(new Headers(fetchMock.mock.calls[0][1]?.headers).get('Authorization')).toBe('Bearer test-token')

    respond({
      order_id: 22, order_type: 'subscribe', status: 'completed', transaction_id: 56,
      balance_fen: 90_000, holding_fen: 10_000, message: '完成',
    })
    await expect(api.executeWealthOrder('test-token', 21)).rejects.toThrow('理财执行结果数据格式异常')
  })

  it('按动作编号执行订阅取消并核对目标订阅', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      subscription_id: 31, status: 'cancelled', message: '模拟订阅已取消。',
    }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.executeSubscriptionCancel('test-token', 12, 31)).resolves.toEqual({
      subscription_id: 31, status: 'cancelled', message: '模拟订阅已取消。',
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/subscriptions/cancel/12/execute', expect.objectContaining({
      method: 'POST', headers: expect.any(Headers),
    }))

    respond({ subscription_id: 32, status: 'cancelled', message: '模拟订阅已取消。' })
    await expect(api.executeSubscriptionCancel('test-token', 12, 31)).rejects.toThrow('订阅取消结果数据格式异常')
  })
})

describe('会话历史游标分页', () => {
  const m = (id: number) => ({ id, role: 'assistant', content: String(id), created_at: '' })

  it('读取最多50条并保留查找更早消息的标志', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(Array.from({ length: 51 }, (_, i) => m(40 + i))), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await api.messagesPage('token', 7)
    expect(result.messages).toHaveLength(50)
    expect(result.messages[0].id).toBe(41)
    expect(result.hasOlder).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/conversations/7/messages?limit=51', expect.anything())
  })

  it('把限定到本会话的游标原样传给后端', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([m(7), m(8)]), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const result = await api.messagesPage('token', 7, 40)
    expect(result.messages.map(message => message.id)).toEqual([7, 8])
    expect(result.hasOlder).toBe(false)
    expect(fetchMock).toHaveBeenCalledWith('/api/chat/conversations/7/messages?limit=51&before_id=40', expect.anything())
  })
})
