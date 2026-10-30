import { useEffect, useRef } from 'react'
import { ArrowUp, Square } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
  onStop?: () => void
}

export function ChatComposer({ value, onChange, onSend, disabled = false, onStop }: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const composingRef = useRef(false)
  const prefersReducedMotion = useReducedMotion()

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 168)}px`
  }, [value])

  const canSend = value.trim().length > 0 && !disabled

  return (
    <motion.form
      layoutId={prefersReducedMotion ? undefined : 'chat-composer'}
      transition={{ type: 'spring', stiffness: 280, damping: 32 }}
      className="mx-auto w-full max-w-[704px]"
      onSubmit={(event) => {
        event.preventDefault()
        if (canSend) onSend()
      }}
    >
      <div className="flex min-h-[64px] items-end gap-2 rounded-[15px] border border-[#dce6e1] bg-white p-2 pl-4 transition-[border-color,box-shadow] focus-within:border-jade-500/70 focus-within:ring-4 focus-within:ring-jade-500/10">
        <Textarea
          ref={textareaRef}
          rows={1}
          value={value}
          placeholder="说说你想办的事"
          className="scroll-thin max-h-[168px] min-h-10 py-2 pr-2"
          onChange={(event) => onChange(event.target.value)}
          onCompositionStart={() => {
            composingRef.current = true
          }}
          onCompositionEnd={() => {
            composingRef.current = false
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey && !composingRef.current) {
              event.preventDefault()
              if (canSend) onSend()
            }
          }}
        />
        {onStop ? <button type="button" onClick={onStop} aria-label="停止接收" title="停止接收" className="grid size-11 shrink-0 place-items-center rounded-xl bg-ink text-white focus-visible:outline-2 focus-visible:outline-jade-700"><Square size={15} fill="currentColor" /></button> : <button
          type="submit"
          disabled={!canSend}
          className={cn(
            'grid size-11 shrink-0 place-items-center rounded-xl transition',
            canSend
              ? 'bg-jade-700 text-white hover:bg-jade-800'
              : 'bg-ink/5 text-muted/45',
          )}
        >
          <ArrowUp className="size-[18px]" strokeWidth={2.3} />
          <span className="sr-only">发送</span>
        </button>}
      </div>
    </motion.form>
  )
}
