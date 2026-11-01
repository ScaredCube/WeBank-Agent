import { animate, motion, useDragControls, useMotionValue, useReducedMotion, type PanInfo } from 'motion/react'
import { useEffect, useRef, useState, type PointerEvent } from 'react'

export function DraggableAccount({ onDrop, onChoose, onMove, onCancel, label, selected = false }: { onDrop: (info: PanInfo) => void; onChoose: () => void; onMove: (info: PanInfo) => void; onCancel: () => void; label: string; selected?: boolean }) {
  const controls = useDragControls()
  const reduced = useReducedMotion()
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const origin = useRef({ x: 0, y: 0 })
  const dragging = useRef(false)
  const suppressClick = useRef(false)
  const [active, setActive] = useState(false)

  function clear() { if (timer.current) clearTimeout(timer.current); timer.current = null }
  function returnToOrigin() {
    const transition = reduced ? { duration: 0 } : { type: 'spring' as const, stiffness: 420, damping: 32 }
    void animate(x, 0, transition)
    void animate(y, 0, transition)
  }
  useEffect(() => () => clear(), [])
  useEffect(() => {
    function cancelOnBlur() {
      clear()
      dragging.current = false
      controls.stop()
      suppressClick.current = true
      setActive(false)
      const transition = reduced ? { duration: 0 } : { type: 'spring' as const, stiffness: 420, damping: 32 }
      void animate(x, 0, transition)
      void animate(y, 0, transition)
      onCancel()
    }
    window.addEventListener('blur', cancelOnBlur)
    return () => window.removeEventListener('blur', cancelOnBlur)
  }, [controls, onCancel, reduced, x, y])

  function down(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return
    // Touch devices use an explicit selection / ask action, not an unmarked drag target.
    if (event.pointerType === 'touch') return
    x.stop()
    y.stop()
    origin.current = { x: event.clientX, y: event.clientY }
    dragging.current = false
    suppressClick.current = false
    clear()
    timer.current = setTimeout(() => { dragging.current = true; suppressClick.current = true; setActive(true); controls.start(event) }, 250)
  }
  function move(event: PointerEvent<HTMLButtonElement>) {
    if (!dragging.current && Math.hypot(event.clientX - origin.current.x, event.clientY - origin.current.y) > 9) clear()
  }

  return <motion.button type="button" aria-pressed={selected} drag dragListener={false} dragControls={controls} dragSnapToOrigin dragMomentum={false}
    style={{ x, y }}
    dragTransition={reduced ? { bounceStiffness: 1000000, bounceDamping: 10000000 } : { bounceStiffness: 420, bounceDamping: 32 }}
    onPointerDown={down} onPointerMove={move} onPointerUp={() => { clear(); setActive(false); if (!dragging.current) returnToOrigin() }} onPointerCancel={() => { clear(); setActive(false); dragging.current = false; returnToOrigin(); onCancel() }}
    onDrag={(_event, info) => onMove(info)}
    onDragEnd={(_event, info) => { clear(); setActive(false); if (dragging.current) onDrop(info); dragging.current = false }}
    onClick={() => { if (!suppressClick.current) onChoose(); suppressClick.current = false }}
    animate={{ scale: active && !reduced ? 1.03 : 1 }} transition={{ type: 'spring', stiffness: 420, damping: 32 }}
    className={`relative z-10 w-full rounded-2xl border p-4 text-left shadow-sm focus-visible:outline-2 focus-visible:outline-jade-700 ${selected ? 'border-jade-600 bg-jade-50' : 'border-jade-200 bg-white'}`}>
    <span className="flex items-center justify-between gap-3"><span className="text-xs text-muted">付款账户</span><span data-drag-handle aria-hidden="true" className="hidden touch-none rounded-lg bg-jade-50 px-3 py-2 text-xs text-jade-800 md:block">长按拖动</span></span><span className="mt-2 block text-sm font-medium">{label}</span>
  </motion.button>
}
