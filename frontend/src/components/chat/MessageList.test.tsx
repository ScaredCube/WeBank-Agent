// @vitest-environment jsdom
import { useRef } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MessageList } from './MessageList'

const messages = [
  { id: 1, role: 'user' as const, content: '帮我分析本月消费', created_at: '' },
  { id: 2, role: 'assistant' as const, content: '已整理消费数据。', created_at: '' },
]

function Harness() {
  const scrollRoot = useRef<HTMLDivElement>(null)
  return <div role="log" aria-label="对话消息" ref={scrollRoot}>
    <MessageList scrollRoot={scrollRoot} messages={messages} streamingText="" thinking={false} />
  </div>
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it('问题已离开视野后才显示关联提示，并支持键盘可达的往返', async () => {
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
    const id = this.getAttribute('data-message-id')
    if (this.getAttribute('role') === 'log') return { top: 0, bottom: 300, height: 300, left: 0, right: 400, width: 400, x: 0, y: 0, toJSON: () => ({}) }
    if (id === '1') return { top: -200, bottom: -120, height: 80, left: 0, right: 400, width: 400, x: 0, y: -200, toJSON: () => ({}) }
    return { top: 20, bottom: 600, height: 580, left: 0, right: 400, width: 400, x: 0, y: 20, toJSON: () => ({}) }
  })
  const jump = vi.fn()
  const oldScroll = HTMLElement.prototype.scrollIntoView
  HTMLElement.prototype.scrollIntoView = jump
  try {
    render(<Harness />)
    const root = screen.getByRole('log')
    Object.defineProperty(root, 'scrollTop', { configurable: true, value: 180, writable: true })
    const goBack = vi.fn()
    Object.defineProperty(root, 'scrollTo', { configurable: true, value: goBack })
    fireEvent.scroll(root)
    const questionButton = await screen.findByRole('button', { name: '回看' })
    expect(screen.getByText('关联问题')).toBeTruthy()
    fireEvent.click(questionButton)
    expect(document.activeElement?.getAttribute('data-message-id')).toBe('1')
    expect(jump).toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '返回刚才阅读的位置' }))
    expect(goBack).toHaveBeenCalledWith(expect.objectContaining({ top: 180 }))
    await waitFor(() => expect(screen.queryByRole('button', { name: '返回刚才阅读的位置' })).toBeNull())
  } finally {
    HTMLElement.prototype.scrollIntoView = oldScroll
  }
})
