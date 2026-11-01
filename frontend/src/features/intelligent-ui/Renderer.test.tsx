// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { IntelligentCard } from './Renderer'

const card = {
  version: 1,
  id: 'expense-demo',
  title: '消费分析',
  source: '合成账单数据',
  observedAt: '2026-10-01T04:00:00Z',
  blocks: [
    { type: 'metric', label: '本月支出', value: 238600, unit: 'CNY_FEN' },
    { type: 'bar_chart', title: '支出类别', rows: [{ label: '餐饮', value: 86200 }, { label: '交通', value: 42000 }] },
    { type: 'action', action: 'open_assets' },
  ],
} as const

afterEach(cleanup)

it('卡片显示指标、图表、来源和合法操作', () => {
  const action = vi.fn()
  render(<IntelligentCard value={card} onAction={action} />)
  expect(screen.getByText('消费分析')).toBeTruthy()
  expect(screen.getByText('¥2,386.00')).toBeTruthy()
  expect(screen.getByText('合成账单数据')).toBeTruthy()
  expect(screen.getAllByTestId('chart-bar')).toHaveLength(2)
  fireEvent.click(screen.getByRole('button', { name: '查看资产' }))
  expect(action).toHaveBeenCalledWith('open_assets')
})

it('金额隐藏后，卡片中不泄露原始指标、图表数值与来源', () => {
  render(<IntelligentCard value={card} hidden />)
  expect(screen.getByText('卡片内容已隐藏')).toBeTruthy()
  expect(screen.queryByText('¥2,386.00')).toBeNull()
  expect(screen.queryByText('餐饮')).toBeNull()
  expect(screen.queryByText('合成账单数据')).toBeNull()
  expect(screen.queryByTestId('chart-bar')).toBeNull()
})

it('不可信结构化卡片失败时安全降级', () => {
  render(<IntelligentCard value={{ id: 'invalid', blocks: [] }} />)
  expect(screen.getByRole('alert').textContent).toContain('无法展示')
})
