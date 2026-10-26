import { useEffect, useRef } from 'react'
import { ArrowUp } from 'lucide-react'

import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  disabled?: boolean
}

export function ChatComposer({ value, onChange, onSend, disabled = false }: ChatComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const composingRef = useRef(false)

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = '0px'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 168)}px`
  }, [value])

  const canSend = value.trim().length > 0 && !disabled

  return (
    <form
      className="mx-auto w-full max-w-[760px]"
      onSubmit={(event) => {
        event.preventDefault()
        if (canSend) onSend()
      }}
    >
      <div className="flex items-end gap-1.5 rounded-2xl border border-line bg-white p-2 pl-3 shadow-[0_1px_2px_rgba(20,26,22,0.04)] transition focus-within:border-jade-500/45 focus-within:ring-4 focus-within:ring-jade-500/6">
        <Textarea
          ref={textareaRef}
          rows={1}
          value={value}
          autoFocus
          placeholder="说说你想办的事"
          className="scroll-thin max-h-[168px] min-h-9 py-1.5 pr-2"
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
        <button
          type="submit"
          disabled={!canSend}
          className={cn(
            'grid size-9 shrink-0 place-items-center rounded-xl transition',
            canSend
              ? 'bg-jade-700 text-white hover:bg-jade-800'
              : 'bg-ink/5 text-muted/45',
          )}
        >
          <ArrowUp className="size-[18px]" strokeWidth={2.3} />
          <span className="sr-only">发送</span>
        </button>
      </div>
    </form>
  )
}
