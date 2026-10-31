// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ChatPage } from './Chat'
import { ApiError, api, type Message } from '@/lib/api'
import * as collectionStore from '@/features/collections/store'
import * as sse from '@/lib/sse'

vi.mock('@/lib/use-auth', () => ({ useAuth: () => ({ token: 'test', user: { id: 1, username: 'test', display_name: '测试' }, logout: vi.fn() }) }))

const conversation = (id: number) => ({ id, title: `会话${id}`, created_at: '', updated_at: '' })
const message = (text: string): Message => ({ id: 1, role: 'assistant', content: text, created_at: '' })
const dashboard = (cardStatus = 'active') => ({
  accounts: [{ account_id: 1, name: '测试卡', masked_number: '****1234', currency: 'CNY', balance_fen: 10000, status: 'active', card_status: cardStatus, can_transfer: true }],
  contacts: [],
  holdings: [],
  risk_profile: { risk_level: 'R2', score: 60, assessed_at: null },
  generated_at: '2026-01-01T00:00:00Z',
})
let releaseSecond: (value: Message[]) => void
let originalScrollIntoView: PropertyDescriptor | undefined
const scrollIntoView = vi.fn()

const messageWithId = (id: number, text: string): Message => ({ id, role: 'assistant', content: text, created_at: '' })

beforeEach(() => {
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', app: 'test', llm: { mode: 'mock', model: 'mock' } })
  vi.spyOn(api, 'conversations').mockResolvedValue([conversation(1), conversation(2), conversation(3)])
  vi.spyOn(api, 'messages').mockImplementation(async (_token, id) => {
    if (id === 2) return new Promise<Message[]>((resolve) => { releaseSecond = resolve })
    return [message(id === 1 ? '第一段对话' : '第三段对话')]
  })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  if (originalScrollIntoView) Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', originalScrollIntoView)
  else Reflect.deleteProperty(HTMLElement.prototype, 'scrollIntoView')
  originalScrollIntoView = undefined
})

it('健康检查失败时不一直显示连接中', async () => {
  vi.mocked(api.health).mockRejectedValueOnce(new Error('不可用'))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  expect(await screen.findByText('无法读取连接状态，仍可尝试发送。')).toBeTruthy()
  expect(screen.queryByText('连接中')).toBeNull()
})

it('从收藏打开对应会话并定位到保存的消息', async () => {
  const user = userEvent.setup()
  originalScrollIntoView = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollIntoView')
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  vi.spyOn(collectionStore, 'listSnapshots').mockResolvedValueOnce([{ id: 'linked', savedAt: '', card: { version: 1, id: 'saved', title: '收藏卡片', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', origin: { conversationId: 3, messageId: 33 }, blocks: [] } }])
  vi.mocked(api.messages).mockImplementation(async (_token, id) => id === 3
    ? [messageWithId(31, '更早的消息'), messageWithId(33, '目标来源消息'), messageWithId(34, '后续消息')]
    : [messageWithId(11, '当前会话消息')])
  render(<MemoryRouter><ChatPage /></MemoryRouter>)

  await screen.findByText('当前会话消息')
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: '收藏' }))
  await user.click(await screen.findByRole('button', { name: /收藏卡片/ }))
  scrollIntoView.mockClear()
  await user.click(screen.getByRole('button', { name: '查看来源会话' }))

  const targetText = await screen.findByText('目标来源消息')
  const targetMessage = targetText.closest('[data-message-id="33"]')
  expect(targetMessage).not.toBeNull()
  expect(await screen.findByText('已定位到收藏的来源消息。')).toBeTruthy()
  expect(document.activeElement).toBe(targetMessage)
  expect(scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
})

it('来源消息不在会话历史时提示可能已删除或无法展示', async () => {
  const user = userEvent.setup()
  vi.spyOn(collectionStore, 'listSnapshots').mockResolvedValueOnce([{ id: 'missing', savedAt: '', card: { version: 1, id: 'saved', title: '已保存卡片', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', origin: { conversationId: 3, messageId: 33 }, blocks: [] } }])
  vi.mocked(api.messages).mockImplementation(async (_token, id) => id === 3 ? [messageWithId(34, '当前仍可查看的消息')] : [messageWithId(11, '当前会话消息')])
  render(<MemoryRouter><ChatPage /></MemoryRouter>)

  await screen.findByText('当前会话消息')
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: '收藏' }))
  await user.click(await screen.findByRole('button', { name: /已保存卡片/ }))
  await user.click(screen.getByRole('button', { name: '查看来源会话' }))

  expect((await screen.findByRole('alert')).textContent).toContain('找不到这条消息')
  expect(screen.getByText('当前仍可查看的消息')).toBeTruthy()
})

it('移动侧栏打开后可用 Escape 关闭并返回入口焦点', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const trigger = screen.getByRole('button', { name: '打开导航和会话列表' })
  await user.click(trigger)
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '收起侧栏' }))
  await user.keyboard('{Escape}')
  expect(document.activeElement).toBe(trigger)
})

it('打开工作面后可用 Escape 返回原入口', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'cards').mockResolvedValue([])
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const trigger = screen.getByRole('button', { name: '打开导航和会话列表' })
  await user.click(trigger)
  await user.click(screen.getByRole('button', { name: '资产' }))
  expect(document.activeElement).toBe(screen.getByRole('button', { name: '收起资产区' }))
  await user.keyboard('{Escape}')
  expect(screen.queryByRole('button', { name: '收起资产区' })).toBeNull()
  expect(document.activeElement).toBe(trigger)
})

it('快速切换时迟到的历史消息不能覆盖当前会话', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.click(screen.getByRole('button', { name: /会话2/ }))
  await user.click(screen.getByRole('button', { name: /会话3/ }))
  await screen.findByText('第三段对话')
  releaseSecond([message('第二段对话')])
  await waitFor(() => expect(screen.queryByText('第二段对话')).toBeNull())
  expect(screen.getByText('第三段对话')).toBeTruthy()
})

it('切换会话历史失败时不展示旧消息，重试成功前不能发送', async () => {
  const user = userEvent.setup()
  vi.mocked(api.messages).mockImplementation(async (_token, id) => {
    if (id === 3) throw new Error('历史加载失败')
    return [message('第一段对话')]
  })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.click(screen.getByRole('button', { name: /会话3/ }))
  await screen.findByText('历史加载失败')
  expect(screen.queryByText('第一段对话')).toBeNull()
  expect((screen.getByRole('button', { name: '发送' }) as HTMLButtonElement).disabled).toBe(true)
  vi.mocked(api.messages).mockResolvedValueOnce([message('第三段对话')])
  await user.click(screen.getByRole('button', { name: '重试加载会话' }))
  expect(await screen.findByText('第三段对话')).toBeTruthy()
  const input = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  expect(input.disabled).toBe(false)
})

it('会话历史加载期间不能新建会话，避免中断当前加载', async () => {
  const user = userEvent.setup()
  const create = vi.spyOn(api, 'createConversation').mockResolvedValue(conversation(4))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.click(screen.getByRole('button', { name: /会话2/ }))
  expect((screen.getByRole('button', { name: '新对话' }) as HTMLButtonElement).disabled).toBe(true)
  expect(create).not.toHaveBeenCalled()
  await act(async () => releaseSecond([message('第二段对话')]))
  await screen.findByText('第二段对话')
  expect((screen.getByRole('button', { name: '新对话' }) as HTMLButtonElement).disabled).toBe(false)
})

it('切换会话后恢复各自的未发送草稿', async () => {
  const user = userEvent.setup()
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const composer = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(composer, '第一份草稿')
  await user.click(screen.getByRole('button', { name: /会话3/ }))
  await screen.findByText('第三段对话')
  expect(composer.value).toBe('')
  await user.type(composer, '第三份草稿')
  await user.click(screen.getByRole('button', { name: /会话1/ }))
  await screen.findByText('第一段对话')
  expect(composer.value).toBe('第一份草稿')
})

it('新建会话期间继续编辑的文字留在原会话草稿中', async () => {
  const user = userEvent.setup()
  let finishCreate!: (result: ReturnType<typeof conversation>) => void
  vi.spyOn(api, 'createConversation').mockImplementation(() => new Promise((resolve) => { finishCreate = resolve }))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const composer = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(composer, '原有')
  await user.click(screen.getByRole('button', { name: '新对话' }))
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '补充')
  await act(async () => { finishCreate(conversation(4)) })
  expect((screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement).value).toBe('')
  await user.click(screen.getByRole('button', { name: /会话1/ }))
  await screen.findByText('第一段对话')
  expect((screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement).value).toBe('原有补充')
})

it('首次发送等待创建会话时继续输入的草稿不会被清除', async () => {
  const user = userEvent.setup()
  let finishCreate!: (result: ReturnType<typeof conversation>) => void
  vi.mocked(api.conversations).mockResolvedValue([])
  vi.spyOn(api, 'createConversation').mockImplementation(() => new Promise((resolve) => { finishCreate = resolve }))
  vi.spyOn(sse, 'streamChat').mockImplementation(() => new Promise(() => {}))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByRole('heading', { name: /今天，想完成什么/ })
  const composer = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(composer, '第一条')
  await user.click(screen.getByRole('button', { name: '发送' }))
  const pendingComposer = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  expect(pendingComposer).not.toBe(composer)
  await user.type(pendingComposer, '下一条')
  await act(async () => { finishCreate(conversation(4)) })
  await waitFor(() => expect((screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement).value).toBe('下一条'))
})

it('暂时关闭待确认动作后可以恢复，且不会重新开放发送', async () => {
  const user = userEvent.setup()
  vi.spyOn(sse, 'streamChat').mockImplementation(async ({ onEvent }) => {
    onEvent({ type: 'action_required', confirmation_token: 'test-token', transfer_id: 42, action: { id: 3, action_type: 'transfer', risk_level: 'yellow', status: 'pending', expires_at: '2030-01-01T00:00:00Z', details: { account_masked: '****8899', recipient_name: '测试收款人', amount_fen: 1250, currency: 'CNY' } } })
  })
  vi.spyOn(api, 'actionStep').mockResolvedValue({ status: 'confirmed', message: '已确认' })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await user.click(await screen.findByRole('button', { name: '确认' }))
  await screen.findByRole('button', { name: '执行操作' })
  await user.click(screen.getByRole('button', { name: '关闭' }))
  expect(screen.getByRole('button', { name: '发送' }).hasAttribute('disabled')).toBe(true)
  expect((screen.getByRole('button', { name: /会话3/ }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '新对话' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('请先处理当前操作，再切换或新建会话。')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '查看待处理操作' }))
  expect(screen.getByRole('button', { name: '执行操作' })).toBeTruthy()
})

it('同一渲染周期的重复提交只发送一次', async () => {
  const user = userEvent.setup()
  const stream = vi.spyOn(sse, 'streamChat').mockImplementation(() => new Promise(() => {}))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const input = screen.getByPlaceholderText('说说你想办的事')
  await user.type(input, '测试请求')
  const form = input.closest('form')!
  act(() => { fireEvent.submit(form); fireEvent.submit(form) })
  expect(stream).toHaveBeenCalledTimes(1)
})

it('停止接收会保留已收到的内容，并说明服务端任务可能继续', async () => {
  const user = userEvent.setup()
  vi.spyOn(sse, 'streamChat').mockImplementation(({ onEvent, signal }) => new Promise<void>((_resolve, reject) => {
    onEvent({ type: 'delta', text: '已经收到的部分' })
    signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await user.click(await screen.findByRole('button', { name: '停止接收' }))
  expect(await screen.findByText('已经收到的部分')).toBeTruthy()
  expect(await screen.findByText(/服务端可能仍在处理/)).toBeTruthy()
})

it('动作事件异常提示不会被后续流错误覆盖', async () => {
  const user = userEvent.setup()
  vi.spyOn(sse, 'streamChat').mockImplementation(async ({ onEvent }) => {
    onEvent({ type: 'action_warning', message: '服务端可能已创建操作，请查看操作记录。' })
    onEvent({ type: 'error', message: '服务暂时不可用' })
  })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  expect(await screen.findByText(/服务端可能已创建操作/)).toBeTruthy()
  expect(screen.getByText('服务暂时不可用')).toBeTruthy()
})

it('停止接收后历史已保存相同片段时不重复展示', async () => {
  const user = userEvent.setup()
  vi.mocked(api.messages).mockResolvedValueOnce([message('第一段对话')]).mockResolvedValueOnce([message('第一段对话'), { id: 99, role: 'assistant', content: '已经收到的部分', created_at: '2026-01-01T00:00:00Z' }])
  vi.spyOn(sse, 'streamChat').mockImplementation(({ onEvent, signal }) => new Promise<void>((_resolve, reject) => {
    onEvent({ type: 'delta', text: '已经收到的部分' })
    signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await user.click(await screen.findByRole('button', { name: '停止接收' }))
  await waitFor(() => expect(screen.getAllByText('已经收到的部分')).toHaveLength(1))
  expect(screen.getByText(/服务端可能仍在处理/)).toBeTruthy()
})

it('旧历史中有相同文字时仍保留本次收到的片段', async () => {
  const user = userEvent.setup()
  vi.mocked(api.messages).mockResolvedValue([message('重复内容')])
  vi.spyOn(sse, 'streamChat').mockImplementation(({ onEvent, signal }) => new Promise<void>((_resolve, reject) => {
    onEvent({ type: 'delta', text: '重复内容' })
    signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true })
  }))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('重复内容')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await user.click(await screen.findByRole('button', { name: '停止接收' }))
  await waitFor(() => expect(screen.getAllByText('重复内容')).toHaveLength(2))
})

it('参数被明确拒绝时恢复未发送的草稿', async () => {
  const user = userEvent.setup()
  vi.spyOn(sse, 'streamChat').mockRejectedValue(new ApiError('请求参数无效', 422))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  const input = screen.getByPlaceholderText('说说你想办的事') as HTMLTextAreaElement
  await user.type(input, '需要保留的内容')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await screen.findByText('请求参数无效')
  expect(input.value).toBe('需要保留的内容')
})

it('已收到的回复不会被暂时缺少该消息的历史回读覆盖', async () => {
  const user = userEvent.setup()
  const reply: Message = { id: 99, role: 'assistant', content: '已收到的回复', created_at: '2026-01-01T00:00:00Z' }
  vi.spyOn(sse, 'streamChat').mockImplementation(async ({ onEvent }) => { onEvent({ type: 'done', message: reply }) })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await waitFor(() => expect(screen.getByText('已收到的回复')).toBeTruthy())
  expect(screen.getByText(/历史记录暂未包含本条回复/)).toBeTruthy()
})

it('历史已包含回复时不会重复显示', async () => {
  const user = userEvent.setup()
  const reply: Message = { id: 99, role: 'assistant', content: '已保存的回复', created_at: '2026-01-01T00:00:00Z' }
  vi.mocked(api.messages).mockResolvedValueOnce([message('第一段对话')]).mockResolvedValueOnce([message('第一段对话'), reply])
  vi.spyOn(sse, 'streamChat').mockImplementation(async ({ onEvent }) => { onEvent({ type: 'done', message: reply }) })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试请求')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await waitFor(() => expect(screen.getAllByText('已保存的回复')).toHaveLength(1))
  expect(screen.queryByText(/历史记录暂未包含本条回复/)).toBeNull()
})

it('模拟挂失完成后重新读取银行卡状态', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'bankDashboard').mockResolvedValueOnce(dashboard()).mockResolvedValue(dashboard('lost'))
  vi.spyOn(api, 'cards').mockResolvedValueOnce([{ card_id: 2, account_name: '测试卡', masked_number: '****1234', status: 'active', account_status: 'active' }]).mockResolvedValue([{ card_id: 2, account_name: '测试卡', masked_number: '****1234', status: 'lost', account_status: 'active' }])
  vi.spyOn(api, 'prepareCardLoss').mockResolvedValue({ action_id: 3, confirmation_token: 'test-token' })
  vi.spyOn(api, 'actionDetails').mockResolvedValue({ id: 3, action_type: 'card_loss', status: 'pending', risk_level: 'red', expires_at: '2030-01-01T00:00:00Z', details: { card_id: 2, masked_number: '****1234' } })
  vi.spyOn(api, 'actionStep').mockResolvedValueOnce({ status: 'pending', message: '验证已开始' }).mockResolvedValueOnce({ status: 'verified', message: '验证通过' })
  vi.spyOn(api, 'executeCardLoss').mockResolvedValue({ status: 'lost' })
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(await screen.findByText('卡片操作'))
  await user.click(await screen.findByRole('button', { name: '模拟挂失' }))
  await user.click(await screen.findByRole('button', { name: '开始模拟验证' }))
  await user.type(screen.getByLabelText('模拟验证码'), '123456')
  await user.click(screen.getByRole('button', { name: '验证' }))
  await user.click(screen.getByRole('button', { name: '执行操作' }))
  await screen.findByText('模拟卡片已挂失。')
  await user.click(screen.getAllByRole('button', { name: '关闭' })[0])
  expect(await screen.findByText('已挂失')).toBeTruthy()
  expect(screen.queryByText('挂失申请已核实，可以继续查看确认步骤。')).toBeNull()
})

it('挂失准备结果未知时切换面板保留申请键，核对使用相同键', async () => {
  const user = userEvent.setup()
  vi.spyOn(api, 'bankDashboard').mockResolvedValue(dashboard())
  vi.spyOn(api, 'cards').mockResolvedValue([{ card_id: 2, account_name: '测试卡', masked_number: '****1234', status: 'active', account_status: 'active' }])
  const prepare = vi.spyOn(api, 'prepareCardLoss').mockRejectedValue(new TypeError('network'))
  render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: '资产' }))
  await user.click(await screen.findByText('卡片操作'))
  await user.click(await screen.findByRole('button', { name: '模拟挂失' }))
  await screen.findByText(/准备结果暂不确定/)
  await user.click(screen.getByRole('button', { name: '收起资产区' }))
  await user.click(screen.getByRole('button', { name: '打开导航和会话列表' }))
  await user.click(screen.getByRole('button', { name: '资产' }))
  expect(await screen.findByText('准备结果暂不确定，请核对申请状态后再决定下一步。')).toBeTruthy()
  await user.click(await screen.findByText('卡片操作'))
  expect(screen.queryByRole('button', { name: '模拟挂失' })).toBeNull()
  expect(screen.getByRole('button', { name: '核对准备结果' })).toBeTruthy()
  expect(screen.getByText(/准备结果暂不确定/)).toBeTruthy()
  expect(prepare).toHaveBeenCalledTimes(1)
  const key = prepare.mock.calls[0][2]
  await user.click(screen.getByRole('button', { name: '核对准备结果' }))
  expect((await screen.findByRole('alert')).textContent).toContain('准备结果暂不确定')
  expect(prepare).toHaveBeenCalledTimes(2)
  expect(prepare.mock.calls[1][2]).toBe(key)
})

it('页面卸载后迟到的会话创建不会继续发送消息', async () => {
  const user = userEvent.setup()
  vi.mocked(api.conversations).mockResolvedValue([])
  let finishCreate!: (value: ReturnType<typeof conversation>) => void
  const pending = new Promise<ReturnType<typeof conversation>>((resolve) => { finishCreate = resolve })
  vi.spyOn(api, 'createConversation').mockReturnValue(pending)
  const stream = vi.spyOn(sse, 'streamChat').mockResolvedValue()
  const page = render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByRole('heading', { name: /今天，想完成什么/ })
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试消息')
  await user.click(screen.getByRole('button', { name: '发送' }))
  page.unmount()
  await act(async () => { finishCreate(conversation(4)); await pending })
  expect(stream).not.toHaveBeenCalled()
})

it('页面卸载时停止接收并且不再回读旧会话', async () => {
  const user = userEvent.setup()
  let abortSeen = false
  vi.spyOn(sse, 'streamChat').mockImplementation(({ signal }) => new Promise<void>((resolve) => {
    signal?.addEventListener('abort', () => { abortSeen = true; resolve() }, { once: true })
  }))
  const page = render(<MemoryRouter><ChatPage /></MemoryRouter>)
  await screen.findByText('第一段对话')
  await user.type(screen.getByPlaceholderText('说说你想办的事'), '测试消息')
  await user.click(screen.getByRole('button', { name: '发送' }))
  await screen.findByRole('button', { name: '停止接收' })
  expect(api.messages).toHaveBeenCalledTimes(1)
  page.unmount()
  await waitFor(() => expect(abortSeen).toBe(true))
  expect(api.messages).toHaveBeenCalledTimes(1)
})
