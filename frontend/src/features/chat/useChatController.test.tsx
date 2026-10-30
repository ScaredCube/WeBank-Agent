// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'

import { ApiError, api, type Message } from '@/lib/api'
import * as sse from '@/lib/sse'
import { useChatController } from './useChatController'

afterEach(() => {
  cleanup()
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
