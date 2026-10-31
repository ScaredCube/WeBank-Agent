// @vitest-environment jsdom
import 'fake-indexeddb/auto'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProductPreview from './ProductPreview'
import * as store from '@/features/collections/store'

let originalScrollIntoView: PropertyDescriptor | undefined
const scrollIntoView = vi.fn()

afterEach(async () => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', originalScrollIntoView)
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
  originalScrollIntoView = undefined
  await store.clearSnapshots(1, 'webank-ui-preview-snapshots')
})

it('合成预览可以查看资产与收藏，且不访问业务接口', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch')
  const user = userEvent.setup()
  const firstRender = render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '资产' }))
  const assets = screen.getByRole('region', { name: '资产' })
  const categories = within(assets).getByRole('navigation', { name: '资产分类' })
  expect(within(categories).getByRole('button', { name: '账户' })).toBeTruthy()
  expect(within(categories).getByRole('button', { name: '联系人' })).toBeTruthy()
  expect(within(categories).getByRole('button', { name: '持仓' })).toBeTruthy()
  await user.click(within(assets).getByRole('button', { name: '查看备用账户详情' }))
  expect(within(assets).getByText('样例卡片状态：正常')).toBeTruthy()
  await user.click(within(assets).getByRole('button', { name: /^付款账户.*日常账户/ }))
  await user.click(within(assets).getByRole('button', { name: /^小林/ }))
  expect(screen.getByText('转账 · 日常账户 → 小林')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '查看模拟确认' }))
  expect(screen.getByText(/合成预览，操作及金额仅为样例/)).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '开始模拟验证' }))
  expect(await screen.findByText('模拟验证已开始，操作尚未执行。')).toBeTruthy()
  await user.type(screen.getByLabelText('模拟验证码'), 'a')
  await user.click(screen.getByRole('button', { name: '验证' }))
  expect(await screen.findByText('样例请输入数字。')).toBeTruthy()
  await user.clear(screen.getByLabelText('模拟验证码'))
  await user.type(screen.getByLabelText('模拟验证码'), '1')
  await user.click(screen.getByRole('button', { name: '验证' }))
  expect(await screen.findByText('模拟验证通过，操作尚未执行。')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '执行操作' }))
  expect(await screen.findByText('合成预览：操作已模拟完成。')).toBeTruthy()
  await user.click(screen.getAllByRole('button', { name: '关闭' })[0])
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '看看转账')
  await user.click(screen.getByRole('button', { name: '发送' }))
  expect(screen.getByText('转账 · 日常账户 → 小林')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '收藏卡片' }))
  await screen.findByText('已收藏合成卡片。')
  await user.click(screen.getByRole('button', { name: '收藏' }))
  expect(await within(screen.getByRole('region', { name: '收藏' })).findByText('本月消费概览')).toBeTruthy()
  firstRender.unmount()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '收藏' }))
  expect(await within(screen.getByRole('region', { name: '收藏' })).findByText('本月消费概览')).toBeTruthy()
  expect(fetchSpy).not.toHaveBeenCalled()
})

it('合成收藏返回原会话并定位到生成卡片的消息', async () => {
  const user = userEvent.setup()
  originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  const view = render(<ProductPreview />)

  await user.click(screen.getByRole('button', { name: '收藏卡片' }))
  await screen.findByText('已收藏合成卡片。')
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  await user.click(screen.getByRole('button', { name: '收藏' }))
  await user.click(await within(screen.getByRole('region', { name: '收藏' })).findByRole('button', { name: /本月消费概览/ }))

  scrollIntoView.mockClear()
  await user.click(screen.getByRole('button', { name: '查看来源会话' }))

  const sourceText = await screen.findByText(/本月支出共/)
  const sourceMessage = sourceText.closest('[data-message-id="2"]')
  expect(sourceMessage).not.toBeNull()
  expect(await screen.findByText('已定位到收藏的来源消息。')).toBeTruthy()
  expect(document.activeElement).toBe(sourceMessage)
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
  view.unmount()
})

it('合成收藏中的来源消息不存在时留在收藏并解释原因', async () => {
  const user = userEvent.setup()
  vi.spyOn(store, 'listSnapshots').mockResolvedValueOnce([{ id: 'missing', savedAt: '', card: { version: 1, id: 'saved', title: '来源消息已失效', source: '合成样例', observedAt: '2026-01-01T00:00:00Z', origin: { conversationId: 1, messageId: 999 }, blocks: [] } }])
  render(<ProductPreview />)

  await user.click(screen.getByRole('button', { name: '收藏' }))
  await user.click(await within(screen.getByRole('region', { name: '收藏' })).findByRole('button', { name: /来源消息已失效/ }))
  await user.click(screen.getByRole('button', { name: '查看来源会话' }))

  expect((await screen.findByRole('alert')).textContent).toContain('找不到这条消息')
  expect(screen.getByRole('button', { name: '返回收藏' })).toBeTruthy()
})

it('切换会话保留各自的草稿', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  const input = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(input, '未完成的想法')
  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  expect(input.value).toBe('')
  await user.click(screen.getByRole('button', { name: /日常财务/ }))
  expect(input.value).toBe('未完成的想法')
})

it('资产工作面按需打开，关闭后焦点返回入口', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)

  expect(screen.queryByRole('region', { name: '资产' })).toBeNull()
  await user.click(screen.getByRole('button', { name: '资产' }))
  expect(screen.getByRole('region', { name: '资产' })).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '收起资产区' }))
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '打开导航和会话列表' }))
})

it('合成卡片保存失败时不声称收藏成功', async () => {
  vi.spyOn(store, 'saveSnapshot').mockRejectedValueOnce(new Error('storage unavailable'))
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '收藏卡片' }))
  expect(await screen.findByText('收藏失败，请检查浏览器存储后重试。')).toBeTruthy()
  expect(screen.queryByText('已收藏合成卡片。')).toBeNull()
})

it('切换会话不会把尚未组合的账户选择带到另一会话', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(screen.getByRole('button', { name: /^付款账户.*日常账户/ }))
  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  await user.click(screen.getByRole('button', { name: /^小林/ }))
  expect(screen.getByText('请先选择付款账户。')).toBeTruthy()
  expect(screen.queryByText('转账 · 日常账户 → 小林')).toBeNull()
})

it('已组合的意图按会话隔离，返回原会话后仍可移除', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(screen.getByRole('button', { name: /^付款账户.*日常账户/ }))
  await user.click(screen.getByRole('button', { name: /^小林/ }))
  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  expect(screen.queryByText('转账 · 日常账户 → 小林')).toBeNull()
  await user.click(screen.getByRole('button', { name: /日常财务/ }))
  expect(screen.getByText('转账 · 日常账户 → 小林')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '移除' }))
  expect(screen.queryByText('转账 · 日常账户 → 小林')).toBeNull()
})

it('不同账户与联系人组合后，确认样例展示对应对象', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(screen.getByRole('button', { name: /^付款账户.*备用账户/ }))
  await user.click(screen.getByRole('button', { name: /^小周/ }))
  expect(screen.getByText('转账 · 备用账户 → 小周')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '查看模拟确认' }))
  expect(screen.getByText('****2631')).toBeTruthy()
  expect(screen.getByText('小周')).toBeTruthy()
})

it('查看账户详情不会隐式选中账户或创建意图', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(screen.getByRole('button', { name: '查看备用账户详情' }))
  await user.click(screen.getByRole('button', { name: /^小周/ }))
  expect(screen.getByText('请先选择付款账户。')).toBeTruthy()
  expect(screen.queryByText('转账 · 备用账户 → 小周')).toBeNull()
})

it('隐藏模式中多个资产可区分但不显示名称与尾号', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.click(screen.getByRole('button', { name: '隐藏金额' }))
  await user.click(screen.getByRole('button', { name: '资产' }))
  expect(screen.getByRole('button', { name: /账户 1 已隐藏/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: /账户 2 已隐藏/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: /联系人 1 已隐藏/ })).toBeTruthy()
  expect(screen.getByRole('button', { name: /联系人 2 已隐藏/ })).toBeTruthy()
  expect(screen.queryByText(/日常账户|备用账户|小林|小周|8899|2631/)).toBeNull()
})

it('不同会话使用不同结构的结果，卡片导航进入工作面', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  expect(screen.getByText('支出分类')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  expect(screen.getByText('银行卡状态')).toBeTruthy()
  const result = screen.getByText('银行卡状态').closest('article')!
  await user.click(within(result).getByRole('button', { name: '查看资产' }))
  expect(screen.getByRole('region', { name: '资产' })).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '收起资产区' }))
  await user.click(screen.getByRole('button', { name: /收支比较/ }))
  expect(screen.getByText('收入')).toBeTruthy()
  expect(screen.getByText('支出')).toBeTruthy()
})

it('合成对话的自然语言摘要与结构化金额一致', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)

  expect(screen.getByText('本月支出共 ¥2,386.00，餐饮金额最高，为 ¥862.00。')).toBeTruthy()
  expect(within(screen.getByRole('article')).getByText('¥2,386.00')).toBeTruthy()

  await user.click(screen.getByRole('button', { name: /卡片与账户/ }))
  expect(screen.getByText('日常账户关联的银行卡（尾号 8899）状态正常。')).toBeTruthy()

  await user.click(screen.getByRole('button', { name: /收支比较/ }))
  expect(screen.getByText('收入 ¥5,200.00，支出 ¥2,386.00，收入高出 ¥2,814.00。')).toBeTruthy()
  const comparison = screen.getByRole('article')
  expect(within(comparison).getByText('¥5,200.00')).toBeTruthy()
  expect(within(comparison).getByText('¥2,386.00')).toBeTruthy()
  expect(screen.queryByText('合成数字仅用于展示结果布局。')).toBeNull()
})

it('上翻阅读时新消息不抢走阅读位置，并显示返回入口', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  const log = screen.getByRole('log')
  Object.defineProperty(log, 'scrollHeight', { configurable: true, value: 1200 })
  Object.defineProperty(log, 'clientHeight', { configurable: true, value: 400 })
  log.scrollTop = 100
  fireEvent.scroll(log)
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '后续问题')
  await user.click(screen.getByRole('button', { name: '发送' }))
  expect(log.scrollTop).toBe(100)
  expect(screen.getByRole('button', { name: '查看新消息' })).toBeTruthy()
  expect(log.textContent!.indexOf('本月消费概览')).toBeLessThan(log.textContent!.indexOf('后续问题'))
})

it('在完整预览中切换空状态和错误状态，不丢失草稿', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  const input = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(input, '保留的草稿')
  await user.selectOptions(screen.getByLabelText('选择预览状态'), 'empty')
  expect(screen.getByRole('heading', { name: /今天，想完成什么/ })).toBeTruthy()
  expect((screen.getByRole('button', { name: '发送' }) as HTMLButtonElement).disabled).toBe(false)
  await user.selectOptions(screen.getByLabelText('选择预览状态'), 'loading')
  expect(screen.getByText('样例：正在加载对话')).toBeTruthy()
  await user.selectOptions(screen.getByLabelText('选择预览状态'), 'error')
  expect(screen.getByText('样例：对话暂时无法加载。')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '恢复样例' }))
  expect((screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement).value).toBe('保留的草稿')
})

it('空状态建议只填入草稿，发送后进入对话布局', async () => {
  const user = userEvent.setup()
  render(<ProductPreview />)
  await user.selectOptions(screen.getByLabelText('选择预览状态'), 'empty')
  await user.click(screen.getByRole('button', { name: /分析本月收支/ }))
  expect((screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement).value).toBe('看看这个月的消费')
  expect(screen.queryByText('这是合成预览，消息不会发送给 Agent。')).toBeNull()
  await user.click(screen.getByRole('button', { name: '发送' }))
  expect(await screen.findByText('这是合成预览，消息不会发送给 Agent。')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: /今天，想完成什么/ })).toBeNull()
})
