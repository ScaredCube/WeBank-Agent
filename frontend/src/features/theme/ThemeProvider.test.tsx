// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ThemeProvider } from './ThemeProvider'
import { useTheme } from './theme-context'
import { ThemeToggle } from './ThemeToggle'

function Probe() {
  const { mode, resolved, setMode } = useTheme()
  return <>
    <output aria-label="主题状态">{mode}:{resolved}</output>
    <button type="button" onClick={() => setMode('system')}>跟随系统</button>
    <ThemeToggle />
  </>
}

afterEach(() => {
  cleanup()
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
  document.documentElement.style.removeProperty('color-scheme')
  vi.unstubAllGlobals()
})

it('两种企鹅主题可切换并保存到本地', async () => {
  render(<ThemeProvider><Probe /></ThemeProvider>)
  expect(screen.getByLabelText('主题状态').textContent).toBe('light:light')
  const toggle = screen.getByRole('button', { name: '切换至深色主题' })
  fireEvent.click(toggle)
  await waitFor(() => expect(screen.getByLabelText('主题状态').textContent).toBe('dark:dark'))
  expect(document.documentElement.dataset.theme).toBe('dark')
  expect(localStorage.getItem('webank-agent-theme')).toBe('dark')
  expect(screen.getByRole('button', { name: '切换至浅色主题' })).toBeTruthy()
})

it('系统主题由系统偏好决定，手动切换后退出系统模式', async () => {
  let onChange: ((event: { matches: boolean }) => void) | undefined
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query === '(prefers-color-scheme: dark)',
    addEventListener: (_type: string, cb: (event: { matches: boolean }) => void) => { onChange = cb },
    removeEventListener: () => {},
  }))
  render(<ThemeProvider><Probe /></ThemeProvider>)
  fireEvent.click(screen.getByRole('button', { name: '跟随系统' }))
  await waitFor(() => expect(screen.getByLabelText('主题状态').textContent).toBe('system:dark'))
  expect(localStorage.getItem('webank-agent-theme')).toBe('system')
  // An explicit toggle overrides system state.
  fireEvent.click(screen.getByRole('button', { name: '切换至浅色主题' }))
  await waitFor(() => expect(screen.getByLabelText('主题状态').textContent).toBe('light:light'))
  expect(onChange).toBeDefined()
})

it('支持时使用缩短的圆形揭幕过渡，主题仍然立即生效', async () => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
  const animate = vi.fn()
  const startViewTransition = vi.fn((callback: () => void) => {
    callback()
    return { ready: Promise.resolve(), finished: Promise.resolve() }
  })
  Object.defineProperty(document, 'startViewTransition', { configurable: true, value: startViewTransition })
  Object.defineProperty(document.documentElement, 'animate', { configurable: true, value: animate })
  try {
    render(<ThemeProvider><Probe /></ThemeProvider>)
    fireEvent.click(screen.getByRole('button', { name: '切换至深色主题' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    expect(startViewTransition).toHaveBeenCalledTimes(1)
    await waitFor(() => expect(animate).toHaveBeenCalledTimes(1))
    expect(animate.mock.calls[0]?.[1]).toMatchObject({
      duration: 460,
      pseudoElement: '::view-transition-new(root)',
    })
  } finally {
    Reflect.deleteProperty(document, 'startViewTransition')
    Reflect.deleteProperty(document.documentElement, 'animate')
  }
})

it('减少动态效果时跳过圆形揭幕', async () => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('prefers-reduced-motion'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }))
  const startViewTransition = vi.fn()
  Object.defineProperty(document, 'startViewTransition', { configurable: true, value: startViewTransition })
  try {
    render(<ThemeProvider><Probe /></ThemeProvider>)
    fireEvent.click(screen.getByRole('button', { name: '切换至深色主题' }))
    await waitFor(() => expect(document.documentElement.dataset.theme).toBe('dark'))
    expect(startViewTransition).not.toHaveBeenCalled()
  } finally {
    Reflect.deleteProperty(document, 'startViewTransition')
  }
})
