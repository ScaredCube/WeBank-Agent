// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { InternalTransferResult } from './InternalTransferResult'
import { PrivacyProvider } from '@/features/privacy/PrivacyProvider'

afterEach(cleanup)

it('renders only a validated server result', () => {
  render(<PrivacyProvider><InternalTransferResult value={{
    transfer_id: 3, status: 'completed', amount_fen: 50000, note: '内部',
    source_name: '工资卡', source_masked: '**** 0001',
    target_name: '零钱账户', target_masked: '**** 0002',
    balance_fen: 450000, currency: 'CNY', transaction_id: 9,
  }} /></PrivacyProvider>)
  expect(screen.getByLabelText('内部转账结果')).toBeTruthy()
  expect(screen.getAllByText('¥500.00').length).toBeGreaterThan(0)
  expect(screen.getByText(/工资卡/)).toBeTruthy()
  expect(screen.getByText(/零钱账户/)).toBeTruthy()
})

it('does not render malformed data', () => {
  render(<PrivacyProvider><InternalTransferResult value={{ transfer_id: 0, status: 'completed' }} /></PrivacyProvider>)
  expect(screen.queryByLabelText('内部转账结果')).toBeNull()
})
