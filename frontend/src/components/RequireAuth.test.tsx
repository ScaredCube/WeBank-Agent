// @vitest-environment jsdom
import { useState } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { RequireAuth } from './RequireAuth'

const auth = vi.hoisted(() => ({ token: 'session-a', sessionVersion: 0 }))
vi.mock('@/lib/use-auth', () => ({ useAuth: () => auth }))
afterEach(() => { cleanup(); auth.token = 'session-a'; auth.sessionVersion = 0 })

function PrivateState() {
  const [value, setValue] = useState('初始内容')
  return <button onClick={() => setValue('旧会话内容')}>{value}</button>
}

it('鉴权会话变化时重新创建私有界面，不保留上一次的内存状态', async () => {
  const user = userEvent.setup()
  const tree = <MemoryRouter><RequireAuth><PrivateState /></RequireAuth></MemoryRouter>
  const view = render(tree)
  await user.click(screen.getByRole('button', { name: '初始内容' }))
  auth.token = 'session-b'
  auth.sessionVersion++
  view.rerender(<MemoryRouter><RequireAuth><PrivateState /></RequireAuth></MemoryRouter>)
  expect(screen.getByRole('button', { name: '初始内容' })).toBeTruthy()
  expect(screen.queryByText('旧会话内容')).toBeNull()
})
