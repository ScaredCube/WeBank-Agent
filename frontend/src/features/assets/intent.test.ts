import { describe, expect, it } from 'vitest'
import { makeIntent } from './intent'

describe('意图组合', () => {
  const account = { type: 'account' as const, id: 'a', label: '工资卡' }
  const contact = { type: 'contact' as const, id: 'b', label: '小林' }
  it('从账户到联系人形成转账意图', () => {
    expect(makeIntent(account, contact)).toEqual({ action: 'transfer', source: account, target: contact })
  })
  it('不支持自身、反向或相同类型组合', () => {
    expect(makeIntent(account, account)).toBeNull()
    expect(makeIntent(contact, account)).toBeNull()
    expect(makeIntent(contact, contact)).toBeNull()
  })
})
