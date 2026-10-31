import { useCallback, useEffect, useRef, useState, type UIEvent } from 'react'
import type { Message } from '@/lib/api'

export function useConversationScroll(messages: Message[], streamingText: string, sending: boolean, loading: boolean) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const followScroll = useRef(true)
  const previousMessages = useRef(messages)
  const [hasNewContent, setHasNewContent] = useState(false)

  useEffect(() => {
    const container = scrollRef.current
    if (container && messages.length === 0 && !streamingText && !sending && !loading) {
      // An empty banking workspace is a top-to-bottom page, not a chat transcript.
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

  const resetScroll = useCallback(() => {
    followScroll.current = true
    setHasNewContent(false)
  }, [])

  function jumpToLatest() {
    resetScroll()
    const container = scrollRef.current
    if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'auto' })
  }

  return { scrollRef, hasNewContent, onScroll, resetScroll, jumpToLatest }
}
