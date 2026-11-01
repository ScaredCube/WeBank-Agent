import { useEffect, useState, type ReactNode, type DragEvent } from 'react'
import { MessageCircle, Grip } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { OBJECT_MIME, type BankObjectReference } from './bank-object-reference'

/** The surface is draggable; a single action is always reachable by keyboard.
 * No instructional footer is repeated under every financial object. */
export function ReferenceSource({ reference, onReference, children, disabled = false }: {
  reference: BankObjectReference
  onReference?: (reference: BankObjectReference) => void
  children: ReactNode
  disabled?: boolean
}) {
  const enabled = Boolean(onReference) && !disabled
  const [canDrag, setCanDrag] = useState(false)
  useEffect(() => {
    const query = window.matchMedia?.('(min-width: 768px) and (pointer: fine)')
    if (!query) return
    const sync = () => setCanDrag(query.matches)
    sync()
    query.addEventListener('change', sync)
    return () => query.removeEventListener('change', sync)
  }, [])
  const reducedMotion = useReducedMotion()
  function startDrag(event: DragEvent<HTMLDivElement>) {
    if (!enabled || !canDrag) { event.preventDefault(); return }
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData(OBJECT_MIME, JSON.stringify(reference))
    event.dataTransfer.setData('text/plain', `${reference.label} ${reference.detail}`)
  }
  return <div className="group/reference bank-reference-source relative" draggable={enabled && canDrag} onDragStart={startDrag}>
    {children}
    {enabled && <div className="absolute bottom-2 right-2 z-[1] flex items-center gap-1">
      <Grip aria-hidden="true" size={14} className="hidden text-muted/60 sm:block" />
      <motion.button type="button" onClick={() => onReference?.(reference)}
        whileHover={reducedMotion ? undefined : { y: -1 }}
        whileTap={reducedMotion ? undefined : { scale: 0.95 }}
        transition={{ type: 'spring', stiffness: 540, damping: 30 }}
        title="引用到对话"
        aria-label={`引用到对话：${reference.label}`}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-lg bg-jade-50 px-3 text-xs font-semibold text-jade-800 shadow-sm transition-colors hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">
        <MessageCircle size={15} aria-hidden="true" />询问
      </motion.button>
    </div>}
  </div>
}
