// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { PageErrorBoundary } from './PageErrorBoundary'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

it('页面加载失败时显示恢复入口', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  function BrokenPage(): never { throw new Error('synthetic failure') }
  render(<PageErrorBoundary><BrokenPage /></PageErrorBoundary>)
  expect(screen.getByRole('alert').textContent).toContain('对话页面暂时无法加载')
  expect(screen.getByRole('button', { name: '刷新页面' })).toBeTruthy()
})
