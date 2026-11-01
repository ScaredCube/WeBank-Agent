import { motion } from 'motion/react'
import { useMotionReduced } from '@/lib/motion'
import { PenguinArt } from './PenguinArt'

/** Decorative mascot artwork with a slow, non-blocking idle. */
export function MascotStage({ compact = false, showcase = false }: { compact?: boolean; showcase?: boolean }) {
  const reduced = useMotionReduced()
  return <motion.div className={'ip-stage relative shrink-0 ' +
    (showcase ? 'size-[290px] xl:size-[330px]' : compact ? 'size-28' : 'size-[116px] sm:size-[178px] lg:size-[218px]')}
    aria-hidden="true"
    animate={reduced ? undefined : { y: [0, -2.5, 0], rotate: [-0.6, 0.6, -0.6] }}
    transition={reduced ? undefined : { duration: 8, repeat: Infinity, ease: 'easeInOut' }}>
    <svg viewBox="0 0 240 240" fill="none" className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden="true">
      <ellipse cx="123" cy="130" rx="97" ry="91" fill="var(--ip-stage-wash)" />
      <path d="M28 161C17 106 56 41 118 28" stroke="var(--color-jade-300)" strokeWidth="1.2" strokeDasharray="3 8" opacity=".55" />
      <path d="M196 78c28 36 20 97-12 124" stroke="var(--color-jade-300)" strokeWidth="1.2" strokeLinecap="round" opacity=".5" />
      <circle cx="40" cy="84" r="4" fill="var(--ip-stage-accent)" />
      <circle cx="209" cy="184" r="3.5" fill="var(--color-jade-400)" />
      <path d="M198 41v19m-9.5-9.5h19" stroke="var(--ip-stage-accent)" strokeWidth="3.5" strokeLinecap="round"/>
      <path d="m28 205 6-9 6 9-6 8-6-8Z" fill="var(--color-jade-300)" opacity=".8"/>
    </svg>
    <div className="absolute inset-[2%]">
      <PenguinArt pose="hero" eager className="size-full drop-shadow-[0_13px_16px_rgba(25,50,43,.09)]" />
    </div>
  </motion.div>
}
