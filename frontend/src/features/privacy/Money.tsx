import { formatCnyFen } from '@/lib/format'
import { cn } from '@/lib/utils'
import { usePrivacy } from './PrivacyProvider'

/** Structured amount from server-issued integer fen. Blur is a visual mask,
 * not an access-control boundary; screen readers get an explicit label. */
export function Money({ fen, currency = 'CNY', className, hidden, peekKey }: {
  fen: number
  currency?: string
  className?: string
  hidden?: boolean
  peekKey?: string
}) {
  const privacy = usePrivacy()
  const masked = hidden ?? privacy.hidden
  const key = peekKey ?? `${fen}:${currency}`
  const visible = !masked || privacy.isRevealed(key)
  const text = currency === 'CNY' ? formatCnyFen(fen) : '金额格式暂不可用'
  return <span
    aria-label={masked && !visible ? '金额已隐藏' : text}
    className={cn('tabular-nums transition-[filter,opacity] duration-300',
      masked && !visible && 'cursor-pointer select-none blur-[6px] opacity-70', className)}
    onClick={masked && !visible ? () => privacy.reveal(key) : undefined}
  >{text}</span>
}
