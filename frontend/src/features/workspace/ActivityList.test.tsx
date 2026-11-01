// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

import type { AuditEntry } from '@/lib/api'
import { ActivityList } from './ActivityList'

afterEach(cleanup)

function entry(id: number, event_type: string, tool?: string): AuditEntry {
  return {
    id,
    event_type,
    tool,
    result: 'success',
    created_at: '2026-10-31T02:00:00Z',
    action_id: null,
  }
}

it('把理财和订阅审计事件转换成具体的业务名称', () => {
  render(<ActivityList entries={[
    entry(1, 'wealth_order_prepared', 'prepare_wealth_subscribe'),
    entry(2, 'wealth_order_completed', 'wealth_redeem'),
    entry(3, 'wealth_order_prepare_failed'),
    entry(4, 'subscription_cancel_prepared'),
    entry(5, 'subscription_cancelled'),
    entry(6, 'subscription_cancel_failed'),
  ]} />)

  expect(screen.getByText('理财申购已准备')).toBeTruthy()
  expect(screen.getByText('模拟理财赎回已完成')).toBeTruthy()
  expect(screen.getByText('理财操作准备失败')).toBeTruthy()
  expect(screen.getByText('取消订阅已准备')).toBeTruthy()
  expect(screen.getByText('模拟订阅已取消')).toBeTruthy()
  expect(screen.getByText('取消订阅失败')).toBeTruthy()
})

it('将已有理财和订阅工具记录显示为用户可读名称', () => {
  render(<ActivityList entries={[
    entry(1, 'tool_called', 'get_wealth_products'),
    entry(2, 'tool_result', 'get_wealth_holdings'),
    entry(3, 'tool_called', 'get_wealth_risk_profile'),
    entry(4, 'tool_called', 'prepare_wealth_subscribe'),
    entry(5, 'tool_called', 'prepare_wealth_redeem'),
    entry(6, 'tool_called', 'wealth_subscribe'),
    entry(7, 'tool_called', 'wealth_redeem'),
    entry(8, 'tool_called', 'get_subscriptions'),
    entry(9, 'tool_called', 'detect_subscriptions'),
    entry(10, 'tool_called', 'prepare_cancel_subscription'),
    entry(11, 'tool_called', 'subscription_cancel'),
  ]} />)

  for (const label of [
    '查询理财产品',
    '查询理财持仓结果',
    '查询理财风险测评',
    '准备理财申购',
    '准备理财赎回',
    '理财申购',
    '理财赎回',
    '查询订阅',
    '识别订阅',
    '准备取消订阅',
    '取消订阅',
  ]) {
    expect(screen.getByText(label)).toBeTruthy()
  }
})
