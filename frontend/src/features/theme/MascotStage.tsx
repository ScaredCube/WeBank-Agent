import { useMotionValue, useReducedMotion, useSpring, motion } from 'motion/react'
import type { PointerEvent } from 'react'
import { PenguinArt } from './PenguinArt'

/** Decorative mascot tracks a nearby pointer gently, then springs home.
 * Motion values bypass React renders during pointer movement.
 */
export function MascotStage({ compact = false, showcase = false }: { compact?: boolean; showcase?: boolean }) {
  const reduceMotion = useReducedMotion()
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const rotate = useMotionValue(0)
  const spring = { stiffness: 170, damping: 19, mass: 0.6 }
  const springX = useSpring(x, spring)
  const springY = useSpring(y, spring)
  const springRotate = useSpring(rotate, spring)

  function move(event: PointerEvent<HTMLDivElement>) {
    if (reduceMotion || event.pointerType !== 'mouse') return
    const rect = event.currentTarget.getBoundingClientRect()
    const dx = (event.clientX - rect.left - rect.width / 2) / (rect.width / 2)
    const dy = (event.clientY - rect.top - rect.height / 2) / (rect.height / 2)
    x.set(Math.max(-8, Math.min(8, dx * 8)))
    y.set(Math.max(-6, Math.min(6, dy * 6)))
    rotate.set(Math.max(-3.6, Math.min(3.6, dx * 3.6)))
  }
  function returnHome() { x.set(0); y.set(0); rotate.set(0) }

  return <div className={'ip-stage relative shrink-0 ' +
    (showcase ? 'size-[290px] xl:size-[330px]' : compact ? 'size-28' : 'size-[116px] sm:size-[178px] lg:size-[218px]')}
    onPointerMove={move} onPointerLeave={returnHome} onPointerCancel={returnHome}
    aria-hidden="true">
    <svg viewBox="0 0 240 240" fill="none" className="pointer-events-none absolute inset-0 size-full overflow-visible" aria-hidden="true">
      <ellipse cx="123" cy="130" rx="97" ry="91" fill="var(--ip-stage-wash)" />
      <path d="M28 161C17 106 56 41 118 28" stroke="var(--color-jade-300)" strokeWidth="1.2" strokeDasharray="3 8" opacity=".55" />
      <path d="M196 78c28 36 20 97-12 124" stroke="var(--color-jade-300)" strokeWidth="1.2" strokeLinecap="round" opacity=".5" />
      <circle cx="40" cy="84" r="4" fill="var(--ip-stage-accent)" />
      <circle cx="209" cy="184" r="3.5" fill="var(--color-jade-400)" />
      <path d="M198 41v19m-9.5-9.5h19" stroke="var(--ip-stage-accent)" strokeWidth="3.5" strokeLinecap="round"/>
      <path d="m28 205 6-9 6 9-6 8-6-8Z" fill="var(--color-jade-300)" opacity=".8"/>
    </svg>
    <motion.div className="absolute inset-[2%]" style={reduceMotion ? undefined : { x: springX, y: springY, rotate: springRotate }}>
      <PenguinArt pose="hero" eager className="ip-stage__mascot size-full drop-shadow-[0_13px_16px_rgba(25,50,43,.09)]" />
    </motion.div>
  </div>
}
