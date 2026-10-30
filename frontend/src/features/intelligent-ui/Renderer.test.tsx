// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IntelligentCard } from './Renderer'

afterEach(cleanup)

describe('受控卡片', () => {
  it('组合指标与明细，并保留来源及查询时间', () => {
    render(<IntelligentCard value={{ version: 1, id: 'bill', title: '账单', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'metric', label: '支出', value: 1250, unit: 'CNY_FEN' }, { type: 'list', rows: [{ label: '餐饮', value: '1 笔' }] }] }} />)
    expect(screen.getByText('¥12.50')).toBeTruthy()
    expect(screen.getByText('餐饮')).toBeTruthy()
    expect(screen.getByText(/账单查询/)).toBeTruthy()
  })

  it('未知组件和非法金额局部降级，不执行内容', () => {
    render(<IntelligentCard value={{ version: 1, id: 'bad', title: '测试', source: '测试', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'script', code: 'alert(1)' }] }} />)
    expect(screen.getByRole('alert').textContent).toContain('无法展示')
  })

  it('隐藏时不渲染指标、明细值和文本块中的内容', () => {
    render(<IntelligentCard hidden value={{ version: 1, id: 'privacy', title: '账单', source: '账单查询', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'metric', label: '支出', value: 1250, unit: 'CNY_FEN' }, { type: 'list', rows: [{ label: '餐饮', value: '¥20.00' }] }, { type: 'text', text: '余额 ¥88.00' }] }} />)
    expect(screen.queryByText('¥12.50')).toBeNull()
    expect(screen.queryByText('¥20.00')).toBeNull()
    expect(screen.queryByText('余额 ¥88.00')).toBeNull()
    expect(screen.getAllByLabelText('内容已隐藏').length).toBe(3)
  })

  it('隐藏模式不会从不可信标题、来源或标签泄露金额', () => {
    const view = render(<IntelligentCard hidden value={{ version: 1, id: 'privacy-labels', title: '余额 ¥999.00', source: '来源 ¥888.00', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'metric', label: '余额 ¥777.00', value: 1250, unit: 'CNY_FEN' }, { type: 'list', rows: [{ label: '金额 ¥666.00', value: '¥20.00' }] }, { type: 'bar_chart', title: '金额 ¥555.00', rows: [{ label: '测试', value: 100 }] }] }} />)
    for (const amount of ['999.00', '888.00', '777.00', '666.00', '555.00', '20.00']) expect(view.container.textContent).not.toContain(amount)
    expect(screen.getByLabelText('图表数值已隐藏')).toBeTruthy()
  })

  it('只分发受控导航动作，不使用描述提供的按钮文案', async () => {
    const user = userEvent.setup()
    const onAction = vi.fn()
    render(<IntelligentCard onAction={onAction} value={{ version: 1, id: 'navigation', title: '卡片', source: '测试', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'action', action: 'open_assets', label: '执行转账' }] }} />)
    await user.click(screen.getByRole('button', { name: '查看资产' }))
    expect(onAction).toHaveBeenCalledWith('open_assets')
    expect(screen.queryByText('执行转账')).toBeNull()
  })

  it('图表展示可读取的数值，隐私模式不泄露条形比例', () => {
    const value = { version: 1, id: 'chart', title: '消费', source: '测试', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'bar_chart', title: '分类', rows: [{ label: '餐饮', value: 1200 }, { label: '出行', value: 0 }] }] }
    const view = render(<IntelligentCard value={value} />)
    expect(screen.getByText('¥12.00')).toBeTruthy()
    expect(screen.getByText('¥0.00')).toBeTruthy()
    view.rerender(<IntelligentCard value={value} hidden />)
    expect(screen.queryByText('¥12.00')).toBeNull()
    expect(screen.getByLabelText('图表数值已隐藏')).toBeTruthy()
    expect(screen.queryByTestId('chart-bar')).toBeNull()
  })

  it('支持受限分组，并在隐藏模式遮盖分组中的金额', async () => {
    const user = userEvent.setup()
    const onAction = vi.fn()
    const value = { version: 1, id: 'group', title: '卡片', source: '测试', observedAt: '2026-01-01T00:00:00Z', blocks: [{ type: 'group', layout: 'columns', blocks: [{ type: 'metric', label: '支出', value: 1250, unit: 'CNY_FEN' }, { type: 'action', action: 'open_assets' }] }] }
    const view = render(<IntelligentCard value={value} onAction={onAction} />)
    expect(screen.getByText('¥12.50')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: '查看资产' }))
    expect(onAction).toHaveBeenCalledWith('open_assets')
    view.rerender(<IntelligentCard value={value} hidden onAction={onAction} />)
    expect(screen.queryByText('¥12.50')).toBeNull()
  })
})
