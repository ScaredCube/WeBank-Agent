import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { ArrowDown, ArrowUp, X } from 'lucide-react'
import { MessageBubble } from '@/components/chat/MessageBubble'
import type { Message } from '@/lib/api'

interface MessageListProps {
  messages: Message[]
  streamingText: string
  thinking: boolean
  renderAfterMessage?: (message: Message) => ReactNode
  scrollRoot?: RefObject<HTMLDivElement | null>
  focusMessageId?: number | null
  onFocusMessageResolved?: (messageId: number, found: boolean) => void
  hasOlder?: boolean
  loadingOlder?: boolean
  onLoadOlder?: () => void
}

type QuestionContext = { id: number; content: string } | null
type ReturnPosition = { scrollTop: number; messageId: number; messageCount: number } | null

function scrollBehavior(): ScrollBehavior {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ? 'instant'
    : 'smooth'
}

/**
 * Keeps long financial results connected to the user's question without
 * permanently taking space away from the chat. Uses the existing scroll root
 * and message IDs; no new routing or global state.
 */
export function MessageList({ messages, streamingText, thinking, renderAfterMessage, scrollRoot, focusMessageId, onFocusMessageResolved, hasOlder, loadingOlder, onLoadOlder }: MessageListProps) {
  const messageRows = useRef(new Map<number, HTMLDivElement>())
  const resolvedFocusId = useRef<number | null>(null)
  const [activeQuestion, setActiveQuestion] = useState<QuestionContext>(null)
  const [returnPosition, setReturnPosition] = useState<ReturnPosition>(null)

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
    target.scrollIntoView?.({ behavior: scrollBehavior(), block: 'center' })
    onFocusMessageResolved?.(focusMessageId, true)
  }, [focusMessageId, messages, onFocusMessageResolved])

  const questions = messages.filter((message) => message.role === 'user')
  // A return target must belong to the current, unchanged message history.
  const validReturnPosition = returnPosition?.messageCount === messages.length ? returnPosition : null

  useEffect(() => {
    const root = scrollRoot?.current
    if (!root || questions.length === 0) return

    let frame = 0
    const update = () => {
      const viewport = root.getBoundingClientRect()
      // Hidden/unmeasured scroll containers have no meaningful question visibility.
      // This also avoids announcing off-screen text before layout is established.
      if (viewport.height <= 0) {
        setActiveQuestion(null)
        return
      }
      const threshold = viewport.top + 32
      let current: QuestionContext = null
      for (const question of questions) {
        const element = messageRows.current.get(question.id)
        if (!element) continue
        if (element.getBoundingClientRect().bottom < threshold) {
          current = { id: question.id, content: question.content }
        }
      }
      setActiveQuestion(previous =>
        previous?.id === current?.id && previous?.content === current?.content ? previous : current)
    }
    const schedule = () => {
      if (frame) return
      frame = window.requestAnimationFrame(() => {
        frame = 0
        update()
      })
    }
    schedule()
    root.addEventListener('scroll', schedule, { passive: true })
    window.addEventListener('resize', schedule)
    return () => {
      root.removeEventListener('scroll', schedule)
      window.removeEventListener('resize', schedule)
      if (frame) window.cancelAnimationFrame(frame)
    }
  // Only message ID/content changes should update this subscription; streaming text
  // is rendered separately and should not re-create scroll listeners on every token.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollRoot, messages])

  const goToQuestion = useCallback(() => {
    const root = scrollRoot?.current
    const question = activeQuestion && messageRows.current.get(activeQuestion.id)
    if (!root || !question) return
    const viewportTop = root.getBoundingClientRect().top
    let currentRow: Message | undefined
    for (const message of messages) {
      const row = messageRows.current.get(message.id)
      if (row && row.getBoundingClientRect().top <= viewportTop + 80) currentRow = message
    }
    setReturnPosition({ scrollTop: root.scrollTop, messageId: currentRow?.id ?? activeQuestion.id, messageCount: messages.length })
    question.focus({ preventScroll: true })
    question.scrollIntoView({ behavior: scrollBehavior(), block: 'start' })
  }, [activeQuestion, messages, scrollRoot])

  const backToResult = useCallback(() => {
    const root = scrollRoot?.current
    if (!root || !validReturnPosition) return
    messageRows.current.get(validReturnPosition.messageId)?.focus({ preventScroll: true })
    root.scrollTo({ top: validReturnPosition.scrollTop, behavior: scrollBehavior() })
    setReturnPosition(null)
  }, [validReturnPosition, scrollRoot])

  return (
    <div className="relative mx-auto w-full max-w-[680px] px-5 py-8 md:px-6 md:py-10">
      {(activeQuestion || validReturnPosition) && <div className="sticky top-2 z-20 -mt-2 mb-5 flex min-h-12 items-center gap-3 rounded-[14px] border border-line bg-panel px-3 py-2 shadow-[0_10px_26px_-21px_rgba(13,37,27,.35)]">
        {validReturnPosition ? <>
          <button type="button" onClick={backToResult}
            className="inline-flex min-h-9 min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-left text-[12px] font-medium text-jade-800 focus-visible:outline-2 focus-visible:outline-jade-700">
            <ArrowDown size={15} className="shrink-0" aria-hidden="true"/> 返回刚才阅读的位置
          </button>
          <button type="button" onClick={() => setReturnPosition(null)} aria-label="关闭返回提示" title="关闭返回提示"
            className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700">
            <X size={15} aria-hidden="true" />
          </button>
        </> : <>
          <span className="min-w-0 flex-1 truncate text-[12px] leading-5 text-muted">
            <span className="mr-2 font-semibold text-ink">关联问题</span>{activeQuestion?.content}
          </span>
          <button type="button" onClick={goToQuestion} className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg px-2 text-[12px] font-semibold text-jade-800 hover:bg-jade-50 focus-visible:outline-2 focus-visible:outline-jade-700">
            <ArrowUp size={14} aria-hidden="true" /> 回看
          </button>
        </>}
      </div>}
      <div className="flex flex-col gap-8">
        {hasOlder && onLoadOlder && <button type="button" disabled={loadingOlder} onClick={onLoadOlder}
          className="mx-auto min-h-10 rounded-full border border-line bg-panel px-4 text-xs font-medium text-jade-800 hover:bg-jade-50 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-jade-700">
          {loadingOlder ? '正在加载更早消息…' : '加载更早消息'}
        </button>}
        {messages.map((message) => (
          <div
            key={message.id}
            ref={(element) => { if (element) messageRows.current.set(message.id, element); else messageRows.current.delete(message.id) }}
            data-message-id={message.id}
            tabIndex={-1}
            className={`flex scroll-mt-24 flex-col gap-4 rounded-2xl focus:outline-none ${focusMessageId === message.id ? 'ring-2 ring-jade-400 ring-offset-4 ring-offset-panel' : ''}`}
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
