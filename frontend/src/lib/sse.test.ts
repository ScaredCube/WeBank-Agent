import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamChat, type StreamEvent } from './sse'

function response(chunks: string[]): Response {
  const encoder = new TextEncoder()
  return new Response(new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(encoder.encode(chunk)); controller.close() } }), { status: 200 })
}

afterEach(() => vi.unstubAllGlobals())

describe('对话流协议', () => {

  it('typed account reference 仅发送账户 ID，可信账单事件可在 done 前送达', async () => {
    const bill = { month: '2026-10', expense_fen: 10000 }
    const stream = [
      'data: '+JSON.stringify({type:'bill_result',data:bill})+'\n\n',
      'data: '+JSON.stringify({type:'done',message:null})+'\n\n',
    ].join('')
    const fetchMock = vi.fn().mockResolvedValue(response([stream]))
    vi.stubGlobal('fetch', fetchMock)
    const events: StreamEvent[] = []
    await streamChat({ token: 'test', conversationId: 5, content: '分析这个账户',
      references: [{kind:'account',id:7,label:'日常账户',detail:'****8899'},
                   {kind:'contact',id:2,label:'小林',detail:'银行'}],
      onEvent: event => events.push(event) })
    const [_, init] = fetchMock.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({content:'分析这个账户',references:[{kind:'account',id:7},{kind:'contact',id:2}]})
    expect(events).toEqual([{type:'bill_result',data:bill},{type:'done',message:null}])
  })

  it('跨分片还原内容并识别结束事件', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"del', 'ta","text":"你好"}\r\n\r\ndata: {"type":"done","message":null}\n\n'])))
    const events: StreamEvent[] = []
    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (event) => events.push(event) })
    expect(events).toEqual([{ type: 'delta', text: '你好' }, { type: 'done', message: null }])
  })

  it('单个异常事件提示用户，同时继续处理其余事件', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {bad}\n\ndata: {"type":"done","message":null}\n\n'])))
    const events: StreamEvent[] = []
    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (event) => events.push(event) })
    expect(events[0]).toMatchObject({ type: 'error', message: expect.stringContaining('异常') })
    expect(events[1]).toEqual({ type: 'done', message: null })
  })

  it('损坏的动作事件提示用户核实服务端状态，并继续处理后续内容', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"action_required","action":{}}\n\ndata: {"type":"delta","text":"后续内容"}\n\ndata: {"type":"done","message":null}\n\n'])))
    const events: StreamEvent[] = []
    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (event) => events.push(event) })
    expect(events[0]).toMatchObject({ type: 'action_warning', message: expect.stringContaining('服务端可能已创建操作') })
    expect(events[1]).toEqual({ type: 'delta', text: '后续内容' })
    expect(events[2]).toEqual({ type: 'done', message: null })
  })

  it.each([
    {
      name: '理财申购', action_type: 'wealth_subscribe', risk_level: 'red', order_id: 24,
      expected: { order_id: 24 },
    },
    {
      name: '理财赎回', action_type: 'wealth_redeem', risk_level: 'red', order_id: 25,
      expected: { order_id: 25 },
    },
    {
      name: '订阅取消', action_type: 'subscription_cancel', risk_level: 'yellow', subscription_id: 31,
      expected: { subscription_id: 31 },
    },
  ])('保留 $name 动作的业务标识', async ({ action_type, risk_level, expected, ...ids }) => {
    const event = {
      type: 'action_required', confirmation_token: 'one-time-token', ...ids,
      action: {
        id: 7, action_type, risk_level, status: 'pending',
        expires_at: '2030-01-01T00:00:00Z', details: {},
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([
      `data: ${JSON.stringify(event)}\n\ndata: {"type":"done","message":null}\n\n`,
    ])))
    const events: StreamEvent[] = []

    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (item) => events.push(item) })

    expect(events[0]).toMatchObject({ type: 'action_required', action: { action_type }, confirmation_token: 'one-time-token', ...expected })
    expect(events[1]).toEqual({ type: 'done', message: null })
  })

  it.each([
    { action_type: 'wealth_subscribe', risk_level: 'red', order_id: undefined },
    { action_type: 'subscription_cancel', risk_level: 'yellow', subscription_id: -1 },
  ])('缺少有效业务标识的 $action_type 动作 fail closed', async ({ action_type, risk_level, order_id, subscription_id }) => {
    const event = {
      type: 'action_required', confirmation_token: 'one-time-token', order_id, subscription_id,
      action: { id: 7, action_type, risk_level, status: 'pending', expires_at: '2030-01-01T00:00:00Z', details: {} },
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([
      `data: ${JSON.stringify(event)}\n\ndata: {"type":"done","message":null}\n\n`,
    ])))
    const events: StreamEvent[] = []

    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (item) => events.push(item) })

    expect(events[0]).toMatchObject({ type: 'action_warning', message: expect.stringContaining('服务端可能已创建操作') })
    expect(events.some((item) => item.type === 'action_required')).toBe(false)
  })

  it('没有结束事件就断流时不能当作正常完成', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"delta","text":"部分内容"}\n\n'])))
    const events: StreamEvent[] = []
    await expect(streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (event) => events.push(event) })).rejects.toThrow(/中断/)
    expect(events).toEqual([{ type: 'delta', text: '部分内容' }])
  })

  it('服务端错误事件是终止状态，不再追加中断错误', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"error","message":"服务不可用"}\n\n'])))
    const events: StreamEvent[] = []
    await streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: (event) => events.push(event) })
    expect(events).toEqual([{ type: 'error', message: '服务不可用' }])
  })

  it('读取网络流失败时说明结果可能未知', async () => {
    const stream = new ReadableStream({ start(controller) { controller.error(new Error('network failure')) } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })))
    await expect(streamChat({ token: 'test', conversationId: 1, content: '测试', onEvent: () => {} })).rejects.toThrow(/连接中断/)
  })
})

it('提交附带稳定 requestId，不在 SSE 内容中泄露金融对象描述', async () => {
  const fetchMock = vi.fn().mockResolvedValue(response(['data: {"type":"done","message":null}\n\n']))
  vi.stubGlobal('fetch', fetchMock)
  await streamChat({
    token:'synthetic-token',conversationId:8,content:'查询账单',
    requestId:'req-sse-unchanged-123',
    references:[{kind:'account',id:12,label:'私人账户',detail:'hidden'}],
    onEvent:()=>{},
  })
  const payload = JSON.parse(fetchMock.mock.calls[0][1].body)
  expect(payload).toEqual({content:'查询账单',request_id:'req-sse-unchanged-123',
    references:[{kind:'account',id:12}]})
  expect(JSON.stringify(payload)).not.toContain('私人账户')
})
