import { useEffect, useRef } from 'react'
import { MessageBubble } from '@/components/chat/MessageBubble'
import type { Message } from '@/lib/api'
import type { ReactNode } from 'react'

interface MessageListProps {
  messages: Message[]
  streamingText: string
  thinking: boolean
  renderAfterMessage?: (message: Message) => ReactNode
  focusMessageId?: number | null
  onFocusMessageResolved?: (messageId: number, found: boolean) => void
}

export function MessageList({ messages, streamingText, thinking, renderAfterMessage, focusMessageId, onFocusMessageResolved }: MessageListProps) {
  const messageRows = useRef(new Map<number, HTMLDivElement>())
  const resolvedFocusId = useRef<number | null>(null)

  useEffect(() => {
    if (focusMessageId == null) {
      resolvedFocusId.current = null
      return
    }
    if (resolvedFocusId.current === focusMessageId) return

    resolvedFocusId.current = focusMessageId
    const target = messageRows.current.get(focusMessageId)
    if (!target) {
      onFocusMessageResolved?.(focusMessageId, false)
      return
    }

    target.focus({ preventScroll: true })
    const reduceMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView?.({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' })
    onFocusMessageResolved?.(focusMessageId, true)
  }, [focusMessageId, messages, onFocusMessageResolved])

  return (
    <div className="mx-auto w-full max-w-[680px] px-5 py-8 md:px-6 md:py-10">
      <div className="flex flex-col gap-8">
        {messages.map((message) => (
          <div
            key={message.id}
            ref={(element) => { if (element) messageRows.current.set(message.id, element); else messageRows.current.delete(message.id) }}
            data-message-id={message.id}
            tabIndex={-1}
            className={`flex scroll-mt-24 flex-col gap-4 rounded-2xl ${focusMessageId === message.id ? 'ring-2 ring-jade-400 ring-offset-4 ring-offset-panel' : ''}`}
          >
            <MessageBubble message={message} />
            {renderAfterMessage?.(message)}
          </div>
        ))}
        {(thinking || streamingText) && (
          <MessageBubble
            message={{
              id: -1,
              role: 'assistant',
              content: streamingText,
              created_at: '',
            }}
            streaming
          />
        )}
      </div>
    </div>
  )
}
