import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'
import { subscribeUnauthorized } from './session'
import { streamChat } from './sse'

afterEach(() => { vi.unstubAllGlobals() })

it('已认证请求返回 401 时通知会话管理', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"未登录"}', { status: 401 })))
  const listener = vi.fn()
  const unsubscribe = subscribeUnauthorized(listener)
  await expect(api.cards('synthetic-token')).rejects.toThrow('未登录')
  expect(listener).toHaveBeenCalledWith('synthetic-token')
  unsubscribe()
})

it('登录失败不会触发现有会话失效通知', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"登录失败"}', { status: 401 })))
  const listener = vi.fn()
  const unsubscribe = subscribeUnauthorized(listener)
  await expect(api.login('synthetic-user', 'synthetic-password')).rejects.toThrow('登录失败')
  expect(listener).not.toHaveBeenCalled()
  unsubscribe()
})

it('对话流返回 401 时通知会话管理', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"未登录"}', { status: 401 })))
  const listener = vi.fn()
  const unsubscribe = subscribeUnauthorized(listener)
  await expect(streamChat({ token: 'synthetic-token', conversationId: 1, content: '测试', onEvent: () => {} })).rejects.toThrow('未登录')
  expect(listener).toHaveBeenCalledWith('synthetic-token')
  unsubscribe()
})
