import { describe, expect, it } from 'vitest'
import { parseIntentMessage } from './intent-message'

describe('意图消息解析', () => {
  it('把服务端生成的胶囊行与用户原文分开', () => {
    expect(parseIntentMessage('【前置意图】转账 · 工资卡 → 张三\n\n800 元，饭钱')).toEqual({
      intent: '转账 · 工资卡 → 张三',
      text: '800 元，饭钱',
    })
  })

  it('普通用户文本保持不变', () => {
    expect(parseIntentMessage('800 元，饭钱')).toEqual({ intent: null, text: '800 元，饭钱' })
    expect(parseIntentMessage('【前置意图】随便写的')).toEqual({ intent: null, text: '【前置意图】随便写的' })
  })
})
