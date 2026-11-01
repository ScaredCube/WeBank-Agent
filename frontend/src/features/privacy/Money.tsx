import { motion } from 'motion/react'
import { formatCnyFen } from '@/lib/format'
import { DURATION, EASE_OUT, useMotionReduced } from '@/lib/motion'
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
  const reduced = useMotionReduced()
  const masked = hidden ?? privacy.hidden
  const key = peekKey ?? `${fen}:${currency}`
  const visible = !masked || privacy.isRevealed(key)
  const obscured = masked && !visible
  const text = currency === 'CNY' ? formatCnyFen(fen) : '金额格式暂不可用'
  return <motion.span
    aria-label={obscured ? '金额已隐藏' : text}
    initial={false}
    animate={reduced ? undefined : {
      filter: obscured ? 'blur(6px)' : 'blur(0px)',
      opacity: obscured ? 0.7 : 1,
    }}
    transition={reduced ? undefined : { duration: DURATION.fast, ease: EASE_OUT }}
    className={cn('tabular-nums',
      obscured && 'cursor-pointer select-none',
      obscured && reduced && 'blur-[6px] opacity-70', className)}
    onClick={obscured ? (event) => { event.stopPropagation(); privacy.reveal(key) } : undefined}
  >{text}</motion.span>
}
