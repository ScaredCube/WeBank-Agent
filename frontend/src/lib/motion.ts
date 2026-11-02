import { useReducedMotion } from 'motion/react'

/** Shared motion vocabulary. Keep UI transitions short and use transform/opacity first. */
export const DURATION = {
  press: 0.12,
  fast: 0.16,
  base: 0.22,
  panel: 0.3,
  drawer: 0.32,
  theme: 0.46,
  celebrate: 0.42,
} as const

export const EASE_OUT: [number, number, number, number] = [0.23, 1, 0.32, 1]
export const EASE_IN_OUT: [number, number, number, number] = [0.77, 0, 0.175, 1]
export const EASE_DRAWER: [number, number, number, number] = [0.32, 0.72, 0, 1]
export const EASE_CELEBRATE: [number, number, number, number] = [0.34, 1.56, 0.64, 1]

export const SPRING_SOFT = { type: 'spring', stiffness: 420, damping: 34, mass: 0.8 } as const
export const SPRING_LIFT = { type: 'spring', stiffness: 520, damping: 32, mass: 0.7 } as const

/** Motion's hook already listens for media changes; this wrapper only normalizes null. */
export function useMotionReduced(): boolean {
  return useReducedMotion() ?? false
}
