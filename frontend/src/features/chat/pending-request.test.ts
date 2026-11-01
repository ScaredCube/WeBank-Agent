// @vitest-environment jsdom
import { beforeEach, expect, it } from 'vitest'
import {
  savePendingChatRequest, clearPendingChatRequest, readPendingChatRequests,
} from './pending-request'

beforeEach(() => sessionStorage.clear())

it('刷新后仅保留请求标识与会话 ID，绝不储存金融数据或原文', () => {
  savePendingChatRequest({conversationId:17,requestId:'req-test-reload-001',createdAt:Date.now()})
  const persisted = JSON.stringify(sessionStorage)
  expect(persisted).not.toContain('account_token')
  expect(readPendingChatRequests()).toEqual([
    {conversationId:17,requestId:'req-test-reload-001',createdAt:expect.any(Number)},
  ])
})

it('支持多个未完成请求，移除单条不会删除其他会话请求', () => {
  savePendingChatRequest({conversationId:1,requestId:'req-pending-1234',createdAt:Date.now()})
  savePendingChatRequest({conversationId:2,requestId:'req-pending-5678',createdAt:Date.now()})
  savePendingChatRequest({conversationId:1,requestId:'req-pending-1234',createdAt:Date.now()})
  expect(readPendingChatRequests()).toHaveLength(2)
  clearPendingChatRequest('req-pending-1234')
  expect(readPendingChatRequests().map(item => item.requestId)).toEqual(['req-pending-5678'])
})

it('异常存储格式、过期请求、无效 ID 均安全清理', () => {
  sessionStorage.setItem('xiaowe:chat-inflight:v1','{broken')
  expect(readPendingChatRequests()).toEqual([])
  savePendingChatRequest({conversationId:1,requestId:'req-expired-1234',createdAt:Date.now()-25*60*60*1000})
  savePendingChatRequest({conversationId:0,requestId:'req-invalid-1234',createdAt:Date.now()})
  expect(readPendingChatRequests()).toEqual([])
  sessionStorage.setItem('xiaowe:chat-inflight:v1',JSON.stringify([
    {conversationId:4,requestId:'req-old-request',createdAt:Date.now()-25*60*60*1000},
    {conversationId:8,requestId:'req-good-1234',createdAt:Date.now()},
  ]))
  expect(readPendingChatRequests()).toEqual([
    {conversationId:8,requestId:'req-good-1234',createdAt:expect.any(Number)},
  ])
})
