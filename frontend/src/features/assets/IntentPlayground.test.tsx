// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntentPlayground } from './IntentPlayground'

afterEach(cleanup)

it('可以通过依次点击组合和移除本地意图', async () => {
  const user = userEvent.setup()
  render(<IntentPlayground />)
  await user.click(screen.getByRole('button', { name: /示例联系人/ }))
  expect(screen.getByText('请先选择付款账户。')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: /示例工资卡/ }))
  await user.click(screen.getByRole('button', { name: /示例联系人/ }))
  expect(screen.getByText('转账')).toBeTruthy()
  await user.click(screen.getByRole('button', { name: '移除' }))
  expect(screen.queryByText('转账')).toBeNull()
})
