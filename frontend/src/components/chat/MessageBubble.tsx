import { BrandMark } from '@/components/BrandMark'
import { Markdown } from '@/components/Markdown'
import type { Message } from '@/lib/api'

export function MessageBubble({
  message,
  streaming = false,
}: {
  message: Message
  streaming?: boolean
}) {
  if (message.role === 'user') {
    return (
      <div className="rise-in flex justify-end">
        <div className="max-w-[82%] whitespace-pre-wrap rounded-2xl rounded-br-[7px] bg-jade-900 px-4 py-2.5 text-[15px] leading-relaxed text-jade-50">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="rise-in flex gap-3">
      <BrandMark className="mt-0.5 size-8 rounded-[9px]" />
      <div className="min-w-0 flex-1 pt-0.5">
        {message.content ? (
          streaming ? (
            <p className="whitespace-pre-wrap text-[15px] leading-[1.78] text-ink">
              {message.content}
              <span className="stream-caret" />
            </p>
          ) : (
            <Markdown content={message.content} />
          )
        ) : (
          <div className="flex h-7 items-center gap-1.5">
            {[0, 1, 2].map((index) => (
              <span
                key={index}
                className="size-1.5 animate-pulse rounded-full bg-muted/35"
                style={{ animationDelay: `${index * 130}ms` }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
