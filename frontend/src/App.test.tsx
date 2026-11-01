// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from './App'

const state = vi.hoisted(() => ({ token: null as string | null }))
vi.mock('@/lib/use-auth', () => ({ useAuth: () => ({ token: state.token }) }))
vi.mock('@/pages/Login', () => ({ LoginPage: () => <div>登录页面</div> }))
vi.mock('@/pages/Chat', () => ({ ChatPage: () => <div>对话页面</div> }))
afterEach(() => { cleanup(); state.token = null; vi.restoreAllMocks() })

it('未登录访问对话时跳转登录页面', async () => {
  render(<MemoryRouter initialEntries={['/chat']}><App /></MemoryRouter>)
  expect(await screen.findByText('登录页面')).toBeTruthy()
  expect(screen.queryByText('对话页面')).toBeNull()
})

it('登录后按需加载对话页面', async () => {
  state.token = 'synthetic-test'
  render(<MemoryRouter initialEntries={['/chat']}><App /></MemoryRouter>)
  expect(await screen.findByText('对话页面')).toBeTruthy()
})

it('合成预览不初始化鉴权或读取浏览器会话', async () => {
  const read = vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
  render(<MemoryRouter initialEntries={['/product-preview']}><App /></MemoryRouter>)
  expect(await screen.findByText('本月消费概览', {}, { timeout: 10000 })).toBeTruthy()
  expect(screen.queryByText('合成预览')).toBeNull()
  // Visual preferences can be read in preview; authentication/session state
  // must remain untouched. This allowlist catches accidental auth reads.
  expect(read.mock.calls.map(([key]) => key).every(
    (key) => key === 'webank-agent-theme' || key === 'webank-agent-panel-width',
  )).toBe(true)
})
