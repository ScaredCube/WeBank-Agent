// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CollectionPanel } from './CollectionPanel'
import * as store from './store'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('切换用户后不显示上一个用户的收藏，也忽略迟到的读取', async () => {
  let finishFirst!: (rows: store.Snapshot[]) => void
  const pending = new Promise<store.Snapshot[]>((resolve) => { finishFirst = resolve })
  vi.spyOn(store, 'listSnapshots').mockReturnValueOnce(pending).mockResolvedValueOnce([])
  const { rerender } = render(<CollectionPanel userId={1} hidden={false} />)
  rerender(<CollectionPanel userId={2} hidden={false} />)
  expect(await screen.findByText('还没有收藏卡片')).toBeTruthy()
  await act(async () => { finishFirst([{ id: 'old', savedAt: '', card: { version: 1, id: 'old', title: '旧用户的卡片', source: '样例', observedAt: '2026-01-01T00:00:00Z', blocks: [] } }]); await pending })
  expect(screen.queryByText('旧用户的卡片')).toBeNull()
})

it('新用户的读取尚未完成时不会显示已加载的旧用户收藏', async () => {
  let finishSecond!: (rows: store.Snapshot[]) => void
  const pending = new Promise<store.Snapshot[]>((resolve) => { finishSecond = resolve })
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'old', savedAt: '', card: { version: 1, id: 'old', title: '旧用户的卡片', source: '样例', observedAt: '2026-01-01T00:00:00Z', blocks: [] } }]).mockReturnValueOnce(pending)
  const { rerender } = render(<CollectionPanel userId={1} hidden={false} />)
  expect(await screen.findByText('旧用户的卡片')).toBeTruthy()
  rerender(<CollectionPanel userId={2} hidden={false} />)
  expect(screen.queryByText('旧用户的卡片')).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('加载中')
  await act(async () => { finishSecond([]); await pending })
  expect(screen.getByText('还没有收藏卡片')).toBeTruthy()
})

it('旧用户的删除完成后不会改变新用户的收藏列表', async () => {
  const user = userEvent.setup()
  const item = (title: string): store.Snapshot => ({ id: 'shared-id', savedAt: '', card: { version: 1, id: 'sample', title, source: '样例', observedAt: '2026-01-01T00:00:00Z', blocks: [] } })
  let finishDelete!: () => void
  const pending = new Promise<void>((resolve) => { finishDelete = resolve })
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([item('旧用户卡片')]).mockResolvedValueOnce([item('新用户卡片')])
  vi.spyOn(store, 'deleteSnapshot').mockReturnValueOnce(pending)
  const { rerender } = render(<CollectionPanel userId={1} hidden={false} />)
  await screen.findByText('旧用户卡片')
  await user.click(screen.getByRole('button', { name: /旧用户卡片/ }))
  await user.click(screen.getByRole('button', { name: '删除' }))
  rerender(<CollectionPanel userId={2} hidden={false} />)
  await screen.findByText('新用户卡片')
  await act(async () => { finishDelete(); await pending })
  expect(screen.getByText('新用户卡片')).toBeTruthy()
})

it('收藏详情返回列表时恢复焦点，损坏记录也可以删除', async () => {
  const user = userEvent.setup()
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'broken', savedAt: '', card: { version: 99 } }])
  const remove = vi.spyOn(store, 'deleteSnapshot').mockResolvedValueOnce()
  render(<CollectionPanel userId={1} hidden={false} />)
  const entry = await screen.findByRole('button', { name: /此卡片数据无法展示/ })
  await user.click(entry)
  expect(screen.getByRole('alert').textContent).toContain('此卡片数据无法展示')
  await user.keyboard('{Escape}')
  expect(document.activeElement).toBe(screen.getByRole('button', { name: /此卡片数据无法展示/ }))
  await user.click(screen.getByRole('button', { name: /此卡片数据无法展示/ }))
  await user.click(screen.getByRole('button', { name: '删除' }))
  expect(remove).toHaveBeenCalledWith(1, 'broken', undefined)
  expect(await screen.findByText('还没有收藏卡片')).toBeTruthy()
  expect(document.activeElement).toBe(screen.getByRole('region', { name: '收藏列表' }))
})

it('只有已知来源的卡片提供会话入口，禁用时不能跳转', async () => {
  const user = userEvent.setup()
  const open = vi.fn()
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'linked', savedAt: '', card: { version: 1, id: 'sample', title: '有来源', source: '样例', observedAt: '2026-01-01T00:00:00Z', origin: { conversationId: 3, messageId: 7 }, blocks: [] } }])
  const view = render(<CollectionPanel userId={1} hidden={false} onOpenSource={open} sourceDisabled />)
  await user.click(await screen.findByRole('button', { name: /有来源/ }))
  expect((screen.getByRole('button', { name: '查看来源会话' }) as HTMLButtonElement).disabled).toBe(true)
  view.rerender(<CollectionPanel userId={1} hidden={false} onOpenSource={open} />)
  await user.click(screen.getByRole('button', { name: '查看来源会话' }))
  expect(open).toHaveBeenCalledWith({ conversationId: 3, messageId: 7 })
})

it('没有来源引用的快照不显示来源会话入口', async () => {
  const user = userEvent.setup()
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'unlinked', savedAt: '', card: { version: 1, id: 'sample', title: '无关联', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', blocks: [] } }])
  render(<CollectionPanel userId={1} hidden={false} onOpenSource={vi.fn()} />)
  await user.click(await screen.findByRole('button', { name: /无关联/ }))
  expect(screen.queryByRole('button', { name: '查看来源会话' })).toBeNull()
  expect(screen.getByRole('status').textContent).toContain('未保存会话来源')
})

it('当前页面不支持来源跳转时说明原因并保留快照详情', async () => {
  const user = userEvent.setup()
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'missing-source', savedAt: '', card: { version: 1, id: 'sample', title: '来源缺失', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', origin: { conversationId: 3, messageId: 7 }, blocks: [] } }])
  render(<CollectionPanel userId={1} hidden={false} />)

  await user.click(await screen.findByRole('button', { name: /来源缺失/ }))

  expect(screen.getByRole('status').textContent).toContain('无法打开已保存的来源消息')
  expect(screen.getByText('收藏时间未知')).toBeTruthy()
})
