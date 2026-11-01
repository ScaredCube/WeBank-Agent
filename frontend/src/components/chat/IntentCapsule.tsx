import { X } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import type { AssetIntent } from '@/features/assets/intent'
import { actionLabel } from '@/features/assets/intent'

export function IntentCapsule({ intent, onRemove }: { intent: AssetIntent; onRemove: () => void }) {
  const reduced = useReducedMotion()
  return <motion.div
    initial={reduced ? false : { opacity: 0, y: 8, scale: 0.98 }}
    animate={{ opacity: 1, y: 0, scale: 1 }}
    exit={reduced ? undefined : { opacity: 0, y: 6, scale: 0.98 }}
    className="mb-2 flex min-h-10 items-center gap-2 rounded-[14px] bg-[#122019] px-3 text-[#F1EDE1] shadow-[0_8px_18px_-10px_rgba(10,20,15,.6)]"
  >
    <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-[#84C8A4] shadow-[0_0_10px_#84C8A4]" />
    <span className="min-w-0 flex-1 truncate text-[12px]">
      <b className="font-semibold text-[#A7D8BC]">{actionLabel(intent.action)}</b>
      <span className="mx-1 opacity-50">·</span>
      {intent.source.label} → {intent.target.label}
    </span>
    <button type="button" onClick={onRemove} aria-label="移除前置意图"
      className="grid size-7 shrink-0 place-items-center rounded-lg text-white/50 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-jade-300">
      <X size={13} />
    </button>
  </motion.div>
}
