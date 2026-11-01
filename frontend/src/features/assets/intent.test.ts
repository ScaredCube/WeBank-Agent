import { describe, expect, it } from 'vitest'
import { resolveIntent, type IntentEntity } from './intent'

const account = (id: number): IntentEntity => ({ kind: 'account', id, label: `卡${id}` })
const contact = (id: number): IntentEntity => ({ kind: 'contact', id, label: `联系人${id}` })
const holding = (id: number): IntentEntity => ({ kind: 'holding', id, label: `持仓${id}` })

describe('资产碰撞矩阵', () => {
  it.each([
    [account(1), account(2), 'internal_transfer'],
    [account(1), contact(1), 'transfer'],
    [contact(1), account(1), 'collect'],
    [account(1), holding(1), 'purchase'],
    [holding(1), account(1), 'redeem'],
    [holding(1), holding(2), 'convert'],
  ])('生成动作 %s → %s', (source, target, action) => {
    expect(resolveIntent(source, target)?.action).toBe(action)
  })

  it('拒绝自拖、未定义组合与禁用实体', () => {
    expect(resolveIntent(account(1), account(1))).toBeNull()
    expect(resolveIntent(contact(1), contact(2))).toBeNull()
    expect(resolveIntent(contact(1), holding(1))).toBeNull()
    expect(resolveIntent({ ...account(1), disabled: true }, contact(1))).toBeNull()
    expect(resolveIntent(account(1), { ...contact(1), disabled: true })).toBeNull()
  })
})
