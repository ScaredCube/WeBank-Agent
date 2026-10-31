import type { ReactNode, DragEvent } from 'react'
import { ArrowUpRight, Grip } from 'lucide-react'
import { OBJECT_MIME, type BankObjectReference } from './bank-object-reference'

export function ReferenceSource({ reference, onReference, children, disabled = false }: {
  reference: BankObjectReference
  onReference?: (reference: BankObjectReference) => void
  children: ReactNode
  disabled?: boolean
}) {
  const enabled = Boolean(onReference) && !disabled
  function startDrag(event: DragEvent<HTMLDivElement>) {
    if (!enabled) { event.preventDefault(); return }
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData(OBJECT_MIME, JSON.stringify(reference))
    event.dataTransfer.setData('text/plain', `${reference.label} ${reference.detail}`)
  }
  return <div className="group/reference relative" draggable={enabled} onDragStart={startDrag}>
    {children}
    {enabled && <div className="mt-1.5 flex items-center justify-between gap-2 px-1 pb-2">
      <span className="inline-flex items-center gap-1 text-[10px] text-muted"><Grip size={12} aria-hidden="true" />可拖入对话</span>
      <button type="button" onClick={() => onReference?.(reference)}
        aria-label={`引用到对话：${reference.label}`}
        className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-3 text-[12px] font-semibold text-jade-800 transition-colors hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700">
        询问此项 <ArrowUpRight size={14} aria-hidden="true" />
      </button>
    </div>}
  </div>
}
