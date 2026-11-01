import { describe, expect, it } from 'vitest'
import { formatCnyFen } from './format'

describe('人民币整数分格式化', () => {
  it('按千位分隔展示元，同时精确保留整数分', () => {
    expect(formatCnyFen(238600)).toBe('¥2,386.00')
    expect(formatCnyFen(12345678)).toBe('¥123,456.78')
    expect(formatCnyFen(Number.MAX_SAFE_INTEGER)).toBe('¥90,071,992,547,409.91')
    expect(formatCnyFen(Number.MAX_SAFE_INTEGER - 1)).toBe('¥90,071,992,547,409.90')
    expect(formatCnyFen(-Number.MAX_SAFE_INTEGER)).toBe('¥-90,071,992,547,409.91')
    expect(formatCnyFen(1)).toBe('¥0.01')
    expect(formatCnyFen(0)).toBe('¥0.00')
  })

  it('拒绝小数和不安全整数', () => {
    expect(() => formatCnyFen(1.5)).toThrow()
    expect(() => formatCnyFen(Number.MAX_SAFE_INTEGER + 1)).toThrow()
  })
})
