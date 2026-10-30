// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MessageList } from './MessageList'

let originalScrollIntoView: PropertyDescriptor | undefined
const scrollIntoView = vi.fn()

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', originalScrollIntoView)
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
  originalScrollIntoView = undefined
})

it('损坏消息显示中性提示，不影响其他消息', () => {
  render(<MessageList messages={[{ id: 1, role: 'user', content: '正常内容', created_at: '' }, { id: -2, role: 'system', content: '', created_at: '', unavailable: true }]} streamingText="" thinking={false} />)
  expect(screen.getByText('正常内容')).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain('此条历史消息无法展示')
})

it('根据来源消息 ID 滚动并聚焦对应消息', () => {
  originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  const onFocusMessageResolved = vi.fn()
  render(<MessageList
    messages={[{ id: 1, role: 'user', content: '上一条', created_at: '' }, { id: 7, role: 'assistant', content: '收藏来源内容', created_at: '' }]}
    streamingText=""
    thinking={false}
    focusMessageId={7}
    onFocusMessageResolved={onFocusMessageResolved}
  />)

  const message = screen.getByText('收藏来源内容').closest('[data-message-id="7"]')
  expect(message).not.toBeNull()
  expect(document.activeElement).toBe(message)
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  expect(onFocusMessageResolved).toHaveBeenCalledWith(7, true)
})

it('来源消息未渲染时报告未找到', () => {
  const onFocusMessageResolved = vi.fn()
  render(<MessageList messages={[{ id: 1, role: 'assistant', content: '只有这一条', created_at: '' }]} streamingText="" thinking={false} focusMessageId={99} onFocusMessageResolved={onFocusMessageResolved} />)
  expect(onFocusMessageResolved).toHaveBeenCalledWith(99, false)
})

it('系统减少动态效果时使用即时滚动', () => {
  originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
  render(<MessageList messages={[{ id: 7, role: 'assistant', content: '收藏来源', created_at: '' }]} streamingText="" thinking={false} focusMessageId={7} />)

  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'auto', block: 'center' })
})

it('消息持续追加时不会重复定位或抢走流式更新的滚动位置', () => {
  originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  const onFocusMessageResolved = vi.fn()
  const { rerender } = render(<MessageList
    messages={[{ id: 7, role: 'assistant', content: '收藏来源', created_at: '' }]}
    streamingText=""
    thinking={false}
    focusMessageId={7}
    onFocusMessageResolved={onFocusMessageResolved}
  />)

  rerender(<MessageList
    messages={[{ id: 7, role: 'assistant', content: '收藏来源', created_at: '' }, { id: 8, role: 'assistant', content: '后续消息', created_at: '' }]}
    streamingText="流式追加"
    thinking={false}
    focusMessageId={7}
    onFocusMessageResolved={onFocusMessageResolved}
  />)

  expect(scrollIntoView).toHaveBeenCalledTimes(1)
  expect(onFocusMessageResolved).toHaveBeenCalledTimes(1)
  expect(document.activeElement).toBe(screen.getByText('收藏来源').closest('[data-message-id="7"]'))
})
