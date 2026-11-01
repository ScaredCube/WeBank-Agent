// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'

import { ApiError, api, type Message } from '@/lib/api'
import * as sse from '@/lib/sse'
import { useChatController } from './useChatController'

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.restoreAllMocks()
})

beforeEach(() => {
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'test', llm: { mode: 'mock', model: 'mock' } })
  vi.spyOn(api, 'conversations').mockResolvedValue([{ id: 1, title: '会话1', created_at: '', updated_at: '' }])
  vi.spyOn(api, 'messages').mockResolvedValue([{ id: 10, role: 'assistant', content: '已有回复', created_at: '' }])
})

it('发送失败且历史未确认新消息时保留原文并提示先核对历史', async () => {
  const stream = vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))
  const raw = '请帮我核对这笔消费'

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(result.current.error).toBe('网络连接中断')
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('请先核对历史记录'))
  expect(result.current.messages).toEqual([{ id: 10, role: 'assistant', content: '已有回复', created_at: '' } satisfies Message])
  expect(stream).toHaveBeenCalledTimes(1)
})

it('发送失败时把原文放在发送期间新草稿前面，不覆盖新输入', async () => {
  let rejectStream!: (error: Error) => void
  let pending!: Promise<void>
  vi.spyOn(sse, 'streamChat').mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectStream = reject }))
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning: vi.fn(),
    onConversationChange: vi.fn(),
  }))
  const raw = '请帮我核对这笔消费'

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  act(() => { pending = result.current.sendMessage(raw) })
  act(() => result.current.updateDraft('下一条草稿'))
  await act(async () => { rejectStream(new TypeError('网络连接中断')); await pending })

  expect(result.current.draft).toBe(`${raw}\n下一条草稿`)
})

it('服务端明确拒绝时也不覆盖发送期间的新草稿', async () => {
  let pending!: Promise<void>
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new ApiError('请求参数无效', 422))
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning: vi.fn(),
    onConversationChange: vi.fn(),
  }))
  const raw = '请帮我核对这笔消费'

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  act(() => { pending = result.current.sendMessage(raw) })
  act(() => result.current.updateDraft('下一条草稿'))
  await act(async () => { await pending })

  expect(result.current.draft).toBe(`${raw}\n下一条草稿`)
  expect(result.current.error).toBe('请求参数无效')
})

it('旧历史里已有同文用户消息时不把它当成本轮已发送', async () => {
  const raw = '请帮我核对这笔消费'
  vi.mocked(api.messages).mockResolvedValue([{ id: 11, role: 'user', content: raw, created_at: '' }])
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('请先核对历史记录'))
})

it('历史回读包含同文用户消息时仍保留草稿并标明来源未知', async () => {
  const raw = '请帮我核对这笔消费'
  const sentMessage: Message = { id: 11, role: 'user', content: raw, created_at: '' }
  vi.mocked(api.messages)
    .mockResolvedValueOnce([{ id: 10, role: 'assistant', content: '已有回复', created_at: '' }])
    .mockResolvedValueOnce([{ id: 10, role: 'assistant', content: '已有回复', created_at: '' }, sentMessage])
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(result.current.messages).toContainEqual(sentMessage)
  expect(result.current.error).toBe('网络连接中断')
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('可能已通过本次请求发送；客户端无法确认来源'))
})

it('回读到其他客户端的新增消息时仍保留本次发送草稿', async () => {
  const raw = '请帮我核对这笔消费'
  const existing: Message = { id: 10, role: 'assistant', content: '已有回复', created_at: '' }
  const otherClientMessage: Message = { id: 11, role: 'user', content: '另一设备发来的消息', created_at: '' }
  vi.mocked(api.messages)
    .mockResolvedValueOnce([existing])
    .mockResolvedValueOnce([existing, otherClientMessage])
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('发送结果暂不确定'))
})

it('按实际发送的 trim 文本识别同文历史，但仍保留原始草稿', async () => {
  const raw = '  请帮我核对这笔消费  '
  const content = raw.trim()
  const existing: Message = { id: 10, role: 'assistant', content: '已有回复', created_at: '' }
  const sentMessage: Message = { id: 11, role: 'user', content, created_at: '' }
  vi.mocked(api.messages)
    .mockResolvedValueOnce([existing])
    .mockResolvedValueOnce([existing, sentMessage])
  const stream = vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(stream).toHaveBeenCalledWith(expect.objectContaining({ content }))
  expect(result.current.draft).toBe(raw)
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('可能已通过本次请求发送；客户端无法确认来源'))
})

it('服务端 SSE 错误事件且历史有同文时仍保留草稿并提示来源不确定', async () => {
  const raw = '请帮我核对这笔消费'
  const existing: Message = { id: 10, role: 'assistant', content: '已有回复', created_at: '' }
  const sentMessage: Message = { id: 11, role: 'user', content: raw, created_at: '' }
  vi.mocked(api.messages)
    .mockResolvedValueOnce([existing])
    .mockResolvedValueOnce([existing, sentMessage])
  vi.spyOn(sse, 'streamChat').mockImplementationOnce(async ({ onEvent }) => {
    onEvent({ type: 'error', message: '模型服务异常' })
  })
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(result.current.error).toBe('模型服务异常')
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('可能已通过本次请求发送；客户端无法确认来源'))
})

it('回读中同时出现匹配与其他用户消息时保留草稿并标为未知', async () => {
  const raw = '请帮我核对这笔消费'
  const existing: Message = { id: 10, role: 'assistant', content: '已有回复', created_at: '' }
  const sentMessage: Message = { id: 11, role: 'user', content: raw, created_at: '' }
  const otherClientMessage: Message = { id: 12, role: 'user', content: '另一设备发来的消息', created_at: '' }
  vi.mocked(api.messages)
    .mockResolvedValueOnce([existing])
    .mockResolvedValueOnce([existing, sentMessage, otherClientMessage])
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('客户端无法确认来源'))
})

it('首次发送前新建会话失败时保留输入并显示错误', async () => {
  vi.mocked(api.conversations).mockResolvedValue([])
  const create = vi.spyOn(api, 'createConversation').mockRejectedValueOnce(new TypeError('网络连接中断'))
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning: vi.fn(),
    onConversationChange: vi.fn(),
  }))
  const raw = '请帮我核对这笔消费'

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(create).toHaveBeenCalledOnce()
  expect(result.current.draft).toBe(raw)
  expect(result.current.error).toBe('网络连接中断')
})

it('异常没有错误文案时仍保留草稿并显示通用结果提示', async () => {
  const onActionWarning = vi.fn()
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError(''))
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token',
    actionBlocked: false,
    onActionRequired: vi.fn(),
    onActionWarning,
    onConversationChange: vi.fn(),
  }))
  const raw = '请帮我核对这笔消费'

  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft(raw))
  await act(async () => { await result.current.sendMessage(raw) })

  expect(result.current.draft).toBe(raw)
  expect(result.current.error).toBe('消息发送失败')
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('发送结果暂不确定'))
})

it('网络失败后同一条消息重试沿用 requestId，新内容改用新 ID', async () => {
  vi.spyOn(api, 'submissionStatus').mockRejectedValue(new ApiError('查询暂不可用', 503))
  const stream = vi.spyOn(sse, 'streamChat').mockRejectedValue(new TypeError('模拟网络中断'))
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token', actionBlocked: false,
    onActionRequired: vi.fn(), onActionWarning: vi.fn(),
    onConversationChange: vi.fn(),
  }))
  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft('查询这个账户的账单'))
  await act(async () => { await result.current.sendMessage('查询这个账户的账单') })
  const firstId = stream.mock.calls[0][0].requestId
  expect(firstId).toMatch(/^[\da-f-]{36}$/i)

  await act(async () => { await result.current.sendMessage('查询这个账户的账单') })
  expect(stream.mock.calls[1][0].requestId).toBe(firstId)

  await act(async () => { await result.current.sendMessage('另一条问题') })
  expect(stream.mock.calls[2][0].requestId).not.toBe(firstId)
})

it('断线后状态查询确认回复已经保存，就恢复历史并消除不确定告警', async () => {
  const saved: Message = { id: 82, role: 'assistant', content: '可信查询完成', created_at: '2026-11-01T00:00:00Z' }
  vi.spyOn(api, 'submissionStatus').mockResolvedValue({
    request_id: 'req-status-test', state: 'completed',
    user_message_id: 42, pending_action_id: null, message: saved,
  })
  const existing: Message = { id: 42, role: 'user', content: '查询消费', created_at: '2026-11-01T00:00:00Z' }
  vi.mocked(api.messages).mockResolvedValueOnce([])
    .mockResolvedValueOnce([existing, saved])
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('连接被切断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token', actionBlocked: false,
    onActionRequired: vi.fn(), onActionWarning, onConversationChange: vi.fn(),
  }))
  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  act(() => result.current.updateDraft('查询消费'))
  await act(async () => { await result.current.sendMessage('查询消费') })
  expect(api.submissionStatus).toHaveBeenCalledWith('synthetic-token', 1, expect.any(String))
  expect(result.current.error).toBeNull()
  expect(result.current.messages).toEqual([existing, saved])
  expect(onActionWarning).not.toHaveBeenCalledWith(expect.stringContaining('发送结果暂不确定'))
})

it('断线后查询得知动作已待确认时，提醒查看操作记录而不重复发起', async () => {
  vi.spyOn(api, 'submissionStatus').mockResolvedValue({
    request_id: 'req-action-test', state: 'action_pending',
    user_message_id: 31, pending_action_id: 99, message: null,
  })
  vi.spyOn(sse, 'streamChat').mockRejectedValueOnce(new TypeError('连接中断'))
  const onActionWarning = vi.fn()
  const { result } = renderHook(() => useChatController({
    token: 'synthetic-token', actionBlocked: false,
    onActionRequired: vi.fn(), onActionWarning, onConversationChange: vi.fn(),
  }))
  await waitFor(() => expect(result.current.loadingMessages).toBe(false))
  await act(async () => { await result.current.sendMessage('准备一笔模拟转账') })
  expect(result.current.error).toBeNull()
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('待确认操作已在服务端创建'))
})

it('刷新挂载时核对历史请求状态，不会向 Agent 重新发送 POST', async () => {
  const oldId = 'req-reload-confirmed-001'
  sessionStorage.setItem('xiaowe:chat-inflight:v1',JSON.stringify([
    {conversationId:1,requestId:oldId,createdAt:Date.now()},
  ]))
  const inspect = vi.spyOn(api,'submissionStatus').mockResolvedValue({
    request_id:oldId,state:'completed',user_message_id:41,
    pending_action_id:null,message:{id:42,role:'assistant',content:'历史回复',created_at:''},
  })
  const stream = vi.spyOn(sse,'streamChat')
  const onActionWarning=vi.fn()
  const {result}=renderHook(()=>useChatController({
    token:'synthetic-token',actionBlocked:false,onActionRequired:vi.fn(),
    onActionWarning,onConversationChange:vi.fn(),
  }))
  await waitFor(()=>expect(result.current.loadingMessages).toBe(false))
  await waitFor(()=>expect(inspect).toHaveBeenCalledWith('synthetic-token',1,oldId))
  expect(stream).not.toHaveBeenCalled()
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('已完成'))
  expect(sessionStorage.getItem('xiaowe:chat-inflight:v1')).toBeNull()
})

it('刷新后待确认的转账仅显示核对提示，不能重新获取确认令牌', async () => {
  sessionStorage.setItem('xiaowe:chat-inflight:v1',JSON.stringify([
    {conversationId:6,requestId:'req-reload-pending-987',createdAt:Date.now()},
  ]))
  const inspect=vi.spyOn(api,'submissionStatus').mockResolvedValue({
    request_id:'req-reload-pending-987',state:'action_pending',
    user_message_id:80,pending_action_id:90,message:null,
  })
  const onActionRequired=vi.fn(),onActionWarning=vi.fn()
  renderHook(()=>useChatController({
    token:'synthetic-token',actionBlocked:false,
    onActionRequired,onActionWarning,onConversationChange:vi.fn(),
  }))
  await waitFor(()=>expect(inspect).toHaveBeenCalledOnce())
  expect(onActionRequired).not.toHaveBeenCalled()
  expect(onActionWarning).toHaveBeenCalledWith(expect.stringContaining('不会再次执行'))
  expect(sessionStorage.getItem('xiaowe:chat-inflight:v1')).toBeNull()
})

it('刷新后处理中请求仅要求核对，不触发工具自动重试', async () => {
  const value={conversationId:7,requestId:'req-reload-processing-01',createdAt:Date.now()}
  sessionStorage.setItem('xiaowe:chat-inflight:v1',JSON.stringify([value]))
  vi.spyOn(api,'submissionStatus').mockResolvedValue({
    request_id:value.requestId,state:'processing',
    user_message_id:11,pending_action_id:null,message:null,
  })
  const send=vi.spyOn(sse,'streamChat'),warning=vi.fn()
  renderHook(()=>useChatController({
    token:'synthetic-token',actionBlocked:false,onActionRequired:vi.fn(),
    onActionWarning:warning,onConversationChange:vi.fn(),
  }))
  await waitFor(()=>expect(warning).toHaveBeenCalledWith(expect.stringContaining('不要重复发起')))
  expect(send).not.toHaveBeenCalled()
  expect(JSON.parse(sessionStorage.getItem('xiaowe:chat-inflight:v1') || '[]')).toHaveLength(1)
})
