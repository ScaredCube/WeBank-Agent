// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MessageBubble } from './MessageBubble'
import { AgentWorkingIndicator } from './AgentWorkingIndicator'

const assistantMessage = {
  id: 8,
  role: 'assistant' as const,
  content: '这是一条可以复制的回答。',
  created_at: '2026-10-01T04:00:00Z',
}

const oldClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
afterEach(() => {
  cleanup()
  if (oldClipboard) Object.defineProperty(navigator, 'clipboard', oldClipboard)
  else Reflect.deleteProperty(navigator, 'clipboard')
})

it('助手回答复制成功后才反馈已复制', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
  render(<MessageBubble message={assistantMessage} />)
  expect(screen.getByText('小We')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '复制回复' }))
  await screen.findByText('已复制')
  expect(writeText).toHaveBeenCalledWith(assistantMessage.content)
})

it('剪贴板不可用时显示失败提示，不虚报成功', async () => {
  Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined })
  render(<MessageBubble message={assistantMessage} />)
  fireEvent.click(screen.getByRole('button', { name: '复制回复' }))
  expect(await screen.findByRole('status')).toHaveProperty('textContent', '复制失败，请手动选择文字')
  expect(screen.queryByText('已复制')).toBeNull()
})

it('工作反馈仅声明实际已知状态，不虚构任务步骤', () => {
  render(<AgentWorkingIndicator label="正在加载对话" />)
  expect(screen.getByRole('status').textContent).toContain('正在加载对话')
  expect(screen.queryByText(/已验证|已执行|完成/)).toBeNull()
})

it('在用户气泡上方展示服务端持久化的前置意图胶囊', () => {
  render(<MessageBubble message={{
    id: 9, role: 'user',
    content: '【前置意图】转账 · 工资卡 → 张三\n\n800 元，饭钱',
    created_at: '2026-10-01T04:00:00Z',
  }} />)
  expect(screen.getByLabelText('前置意图：转账 · 工资卡 → 张三')).toBeTruthy()
  expect(screen.getByText('800 元，饭钱')).toBeTruthy()
  expect(screen.queryByText(/【前置意图】/)).toBeNull()
})
