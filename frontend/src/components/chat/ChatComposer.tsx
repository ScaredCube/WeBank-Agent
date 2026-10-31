import { useLayoutEffect, useRef, useState, type DragEvent } from 'react'
import { ArrowUp, Square, X } from 'lucide-react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import { OBJECT_MIME, parseDroppedReference, referenceKindLabel, type BankObjectReference } from '@/features/references/bank-object-reference'

interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  onStop?: () => void
  variant?: 'home' | 'conversation'
  references?: BankObjectReference[]
  onReferenceDrop?: (value: BankObjectReference) => void
  onRemoveReference?: (value: BankObjectReference) => void
}

export function ChatComposer({ value, onChange, onSend, disabled = false, onStop, variant = 'conversation',
  references = [], onReferenceDrop, onRemoveReference }: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const composingRef = useRef(false)
  const prefersReducedMotion = useReducedMotion()
  const [dropActive, setDropActive] = useState(false)

  useLayoutEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 168)}px`
  }, [value])

  const home = variant === 'home'
  const canSend = value.trim().length > 0 && !disabled
  function onDragOver(event: DragEvent<HTMLFormElement>) {
    if (!onReferenceDrop || !event.dataTransfer.types.includes(OBJECT_MIME)) return
    event.preventDefault()
    event.dataTransfer.dropEffect = 'copy'
    setDropActive(true)
  }
  function onDrop(event: DragEvent<HTMLFormElement>) {
    if (!event.dataTransfer.types.includes(OBJECT_MIME) || !onReferenceDrop) return
    event.preventDefault()
    setDropActive(false)
    const ref = parseDroppedReference(event.dataTransfer.getData(OBJECT_MIME))
    if (!ref) return
    onReferenceDrop(ref)
    textareaRef.current?.focus()
  }
  return <motion.form
    layoutId={prefersReducedMotion ? undefined : 'chat-composer'}
    transition={{ type: 'spring', stiffness: 280, damping: 32 }}
    className={cn('mx-auto w-full', home ? 'max-w-none' : 'max-w-[704px]')}
    onDragOver={onDragOver}
    onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDropActive(false) }}
    onDrop={onDrop}
    onSubmit={(event) => { event.preventDefault(); if (canSend) onSend() }}
  >
    <motion.div data-object-dropzone
      animate={dropActive && !prefersReducedMotion ? { scale: 1.008 } : { scale: 1 }}
      transition={{ type: 'spring', stiffness: 570, damping: 34, mass: 0.6 }}
      className={cn(
      'relative rounded-[21px] border border-line bg-panel p-2.5 transition-[border-color,box-shadow,background-color] focus-within:border-jade-500 focus-within:ring-4 focus-within:ring-jade-500/10',
      home ? 'min-h-[92px] shadow-[0_14px_40px_-32px_rgba(0,48,36,.4)]' : 'min-h-[76px]',
      dropActive && 'border-jade-600 bg-jade-50 ring-4 ring-jade-500/15',
    )}>
      {references.length > 0 && <div aria-label="已引用的金融对象" className="flex flex-wrap gap-2 px-2 pb-2 pt-1">
        <AnimatePresence initial={false}>
        {references.map(ref => <motion.span key={`${ref.kind}:${ref.id}`}
          layout={!prefersReducedMotion}
          initial={prefersReducedMotion ? false : { opacity: 0, scale: 0.88, y: 5 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={prefersReducedMotion ? undefined : { opacity: 0, scale: 0.88, y: -3 }}
          transition={{ type: "spring", stiffness: 520, damping: 31 }}
          className="inline-flex min-h-9 items-center gap-2 rounded-lg border border-jade-200 bg-jade-50 px-2.5 py-1 text-xs text-jade-900">
          <span className="font-semibold">{referenceKindLabel(ref.kind)}</span>
          <span className="max-w-[140px] truncate">{ref.label}</span>
          <button type="button" aria-label={`移除引用：${ref.label}`} onClick={() => onRemoveReference?.(ref)}
            className="grid size-6 shrink-0 place-items-center rounded-md hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">
            <X size={14} aria-hidden="true"/>
          </button>
        </motion.span>)}
        </AnimatePresence>
      </div>}
      <div className="flex items-end gap-2">
        <Textarea ref={textareaRef} rows={1} value={value}
          placeholder={references.length ? '围绕所选对象，想了解什么？' : '说说你想办的事'}
          aria-label="输入消息"
          className="chat-composer-input max-h-[168px] min-h-10 flex-1 overflow-y-auto py-2 pl-2 pr-2"
          onChange={(event) => onChange(event.target.value)}
          onCompositionStart={() => { composingRef.current = true }}
          onCompositionEnd={() => { composingRef.current = false }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !composingRef.current) {
              event.preventDefault(); if (canSend) onSend()
            }
          }}
        />
        {onStop ? <button type="button" onClick={onStop} aria-label="停止接收" title="停止接收" className="grid size-11 shrink-0 place-items-center rounded-xl bg-ink text-white focus-visible:outline-2 focus-visible:outline-jade-700">
          <Square size={15} fill="currentColor" />
        </button> : <motion.button type="submit" disabled={!canSend} aria-label="发送"
          whileHover={prefersReducedMotion || !canSend ? undefined : { scale: 1.05 }}
          whileTap={prefersReducedMotion || !canSend ? undefined : { scale: 0.89 }}
          transition={{ type: "spring", stiffness: 620, damping: 30, mass: 0.5 }}
          className={cn('grid size-11 shrink-0 place-items-center rounded-xl transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700',
            canSend ? 'bg-jade-700 text-white hover:bg-jade-800' : 'bg-ink/5 text-muted/45')}>
          <ArrowUp className="size-[18px]" strokeWidth={2.3} />
        </motion.button>}
      </div>
      {dropActive && <div aria-hidden="true" className="pointer-events-none absolute inset-0 grid place-items-center rounded-[20px] border-2 border-dashed border-jade-600 bg-panel/90 text-sm font-semibold text-jade-800">释放以引用到对话</div>}
    </motion.div>
    {references.length > 0 && <p className="mt-1.5 px-2 text-[11px] leading-5 text-muted">对象是待核验的提问线索；发送前可移除。交易仍需单独确认。</p>}
  </motion.form>
}
