import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react'
import type { Message } from '@/lib/api'

export function useConversationScroll(messages: Message[], streamingText: string, sending: boolean, loading: boolean) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const followScroll = useRef(true)
  // Opening a saved conversation begins at the first message, not the last.
  const pendingPosition = useRef<'top' | 'bottom' | null>('top')
  const previousMessages = useRef(messages)
  const [hasNewContent, setHasNewContent] = useState(false)

  useEffect(() => {
    const container = scrollRef.current
    if (container && pendingPosition.current !== null) {
      if (!loading) {
        const position = pendingPosition.current
        container.scrollTop = position === 'top' ? 0 : container.scrollHeight
        followScroll.current = position === 'bottom' || container.scrollHeight <= container.clientHeight + 80
        pendingPosition.current = null
      }
    } else if (container && messages.length === 0 && !streamingText && !sending && !loading) {
      // The empty workspace begins at the top, never at stale transcript position.
      container.scrollTop = 0
      followScroll.current = true
      setHasNewContent(false)
    } else if (container && followScroll.current) container.scrollTop = container.scrollHeight
    else if (container && (streamingText || sending || messages !== previousMessages.current)) setHasNewContent(true)
    previousMessages.current = messages
  }, [messages, streamingText, sending, loading])

  function onScroll(event: UIEvent<HTMLDivElement>) {
    const element = event.currentTarget
    followScroll.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80
    if (followScroll.current) setHasNewContent(false)
  }

  const resetScroll = useCallback((position: 'top' | 'bottom' = 'bottom') => {
    pendingPosition.current = position
    followScroll.current = position === 'bottom'
    setHasNewContent(false)
    if (position === 'top' && scrollRef.current) scrollRef.current.scrollTop = 0
  }, [])

  function jumpToLatest() {
    resetScroll()
    const container = scrollRef.current
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'auto' })
  }

  return { scrollRef, hasNewContent, onScroll, resetScroll, jumpToLatest }
}
