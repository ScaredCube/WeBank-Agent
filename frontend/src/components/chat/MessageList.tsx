import { MessageBubble } from '@/components/chat/MessageBubble'
import type { Message } from '@/lib/api'

interface MessageListProps {
  messages: Message[]
  streamingText: string
  thinking: boolean
}

export function MessageList({ messages, streamingText, thinking }: MessageListProps) {
  return (
    <div className="mx-auto w-full max-w-[760px] px-5 py-8 md:px-6 md:py-10">
      <div className="flex flex-col gap-8">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
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
