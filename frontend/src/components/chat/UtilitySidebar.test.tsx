// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { UtilitySidebar } from './UtilitySidebar'

afterEach(cleanup)

const conversations = [
  { id: 3, title: '查询银行卡状态', created_at: '2026-10-30T09:00:00', updated_at: '2026-10-30T09:00:00' },
  { id: 4, title: '本月账单分析', created_at: '2026-10-31T09:00:00', updated_at: '2026-10-31T09:00:00' },
]

function sidebar(overrides: Partial<Parameters<typeof UtilitySidebar>[0]> = {}) {
  const onSelect = vi.fn()
  const onNew = vi.fn()
  const onRename = vi.fn(async () => undefined)
  const onTabChange = vi.fn()
  render(<UtilitySidebar
    tab="conversations"
    onTabChange={onTabChange}
    conversations={conversations}
    activeId={3}
    user={{ id: 1, username: 'demo', display_name: '用户' }}
    collections={<p>收藏内容</p>}
    activity={<p>操作记录内容</p>}
    onSelect={onSelect}
    onNew={onNew}
    onRename={onRename}
    onClose={vi.fn()}
    onLogout={vi.fn()}
    {...overrides}
  />)
  return { onRename, onSelect, onNew, onTabChange }
}

it('最近对话可以独立搜索并切换，不触发管理入口', async () => {
  const user = userEvent.setup()
  const actions = sidebar()
  await user.type(screen.getByPlaceholderText('搜索对话'), '账单')
  expect(screen.getByRole('button', { name: /本月账单分析，更新于/ })).toBeTruthy()
  expect(screen.queryByRole('button', { name: /查询银行卡状态，更新于/ })).toBeNull()
  await user.click(screen.getByRole('button', { name: /本月账单分析，更新于/ }))
  expect(actions.onSelect).toHaveBeenCalledWith(4)
  await user.click(screen.getByRole('button', { name: '新对话' }))
  expect(actions.onNew).toHaveBeenCalledTimes(1)
})

it('管理菜单通过服务端回调修改标题，不误选会话', async () => {
  const user = userEvent.setup()
  const actions = sidebar()
  await user.click(screen.getAllByRole('button', { name: '管理会话' })[0])
  await user.click(screen.getByRole('button', { name: '重命名' }))
  await user.clear(screen.getByRole('textbox', { name: '会话名称' }))
  await user.type(screen.getByRole('textbox', { name: '会话名称' }), '家庭账本')
  await user.click(screen.getByRole('button', { name: '保存' }))
  expect(actions.onRename).toHaveBeenCalledWith(expect.any(Number), '家庭账本')
  expect(actions.onSelect).not.toHaveBeenCalled()
})

it('顶部三分段可切换到收藏和操作记录', async () => {
  const user = userEvent.setup()
  const actions = sidebar()
  await user.click(screen.getByRole('button', { name: '收藏' }))
  expect(actions.onTabChange).toHaveBeenCalledWith('collections')
  await user.click(screen.getByRole('button', { name: '操作记录' }))
  expect(actions.onTabChange).toHaveBeenCalledWith('activity')
})

it('当前分段直接渲染对应内容', () => {
  sidebar({ tab: 'collections' })
  expect(screen.getByText('收藏内容')).toBeTruthy()
  cleanup()
  sidebar({ tab: 'activity' })
  expect(screen.getByText('操作记录内容')).toBeTruthy()
})
