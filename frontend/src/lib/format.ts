const cnyIntegerFormatter = new Intl.NumberFormat('zh-CN', {
  useGrouping: true,
  maximumFractionDigits: 0,
})

export function formatCnyFen(fen: number): string {
  if (!Number.isSafeInteger(fen)) throw new RangeError('金额必须是安全范围内的整数分')
  const amount = BigInt(fen)
  const absolute = amount < 0n ? -amount : amount
  const yuan = cnyIntegerFormatter.format(absolute / 100n)
  return `¥${amount < 0n ? '-' : ''}${yuan}.${String(absolute % 100n).padStart(2, '0')}`
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minute = 60 * 1000
  const day = 24 * 60 * minute

  if (diff < minute) return '刚刚'
  if (diff < 60 * minute) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < day && date.getDate() === now.getDate()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  if (diff < 7 * day) {
    return date.toLocaleDateString('zh-CN', { weekday: 'short' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
