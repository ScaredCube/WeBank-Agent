// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { LoginPage } from './Login'

const login = vi.fn()
vi.mock('@/lib/use-auth', () => ({ useAuth: () => ({ token: null, login }) }))
afterEach(() => { cleanup(); login.mockReset() })

it('登录表单默认不填写凭据，字段均有可访问的名称', () => {
  render(<MemoryRouter><LoginPage /></MemoryRouter>)
  expect((screen.getByLabelText('账号') as HTMLInputElement).value).toBe('')
  expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe('')
  expect((screen.getByRole('button', { name: '登录' }) as HTMLButtonElement).disabled).toBe(true)
})

it('登录失败显示错误并允许用户重新提交', async () => {
  login.mockRejectedValueOnce(new Error('暂时无法登录'))
  const user = userEvent.setup()
  render(<MemoryRouter><LoginPage /></MemoryRouter>)
  await user.type(screen.getByLabelText('账号'), 'sample-user')
  await user.type(screen.getByLabelText('密码'), 'sample-input')
  await user.click(screen.getByRole('button', { name: '登录' }))
  expect((await screen.findByRole('alert')).textContent).toBe('暂时无法登录')
  expect((screen.getByRole('button', { name: '登录' }) as HTMLButtonElement).disabled).toBe(false)
})
