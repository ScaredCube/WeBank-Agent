// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CardStatusResult } from './CardStatusResult'

afterEach(cleanup)
const snapshot = {cards:[
  {card_id:1,account_name:'日常账户',masked_number:'**** 0001',status:'active',account_status:'active'},
  {card_id:2,account_name:'另一张卡',masked_number:'**** 0009',status:'lost',account_status:'active'},
]}

it('展示可信银行卡状态及资产入口', () => {
  const open = vi.fn()
  render(<CardStatusResult value={snapshot} onOpenAssets={open}/>)
  expect(screen.getByRole('region',{name:'银行卡状态结果'})).toBeTruthy()
  expect(screen.getByText('日常账户')).toBeTruthy()
  expect(screen.getByText('**** 0001')).toBeTruthy()
  expect(screen.getByText('状态正常')).toBeTruthy()
  expect(screen.getByText('已挂失')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'查看资产'}))
  expect(open).toHaveBeenCalledOnce()
})

it('隐私模式遮蔽账户名称和尾号但保留状态', () => {
  render(<CardStatusResult value={snapshot} hidden/>)
  expect(screen.queryByText('日常账户')).toBeNull()
  expect(screen.queryByText('**** 0001')).toBeNull()
  expect(screen.getByText('已挂失')).toBeTruthy()
})

it('无效卡片标识不会被展示', () => {
  render(<CardStatusResult value={{cards:[{...snapshot.cards[0],card_id:0}]}}/>)
  expect(screen.getByRole('alert')).toBeTruthy()
  expect(screen.queryByText('日常账户')).toBeNull()
})

it('空数组不合成卡片', () => {
  render(<CardStatusResult value={{cards:[]}}/>)
  expect(screen.getByText('未查询到银行卡。')).toBeTruthy()
})
