import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import { Markdown } from '@/components/Markdown'
import { AgentWorkingIndicator } from '@/components/chat/AgentWorkingIndicator'
import { PenguinArt } from '@/features/theme/PenguinArt'
import type { Message } from '@/lib/api'
import { presentReferenceMessage } from '@/features/references/bank-object-reference'

export function MessageBubble({
  message,
  streaming = false,
}: {
  message: Message
  streaming?: boolean
}) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle')

  async function copyAnswer() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(message.content)
      setCopyState('copied')
    } catch {
      setCopyState('failed')
    }
  }

  if (message.unavailable) return <div role="status" className="rounded-xl border border-line bg-panel px-4 py-3 text-sm text-muted">此条历史消息无法展示。</div>
  if (message.role === 'user') {
    const visible = presentReferenceMessage(message.content)
    return <div className="rise-in flex justify-end">
      <div className="max-w-[90%] whitespace-pre-wrap break-words rounded-[17px] rounded-br-[7px] border border-line/50 bg-message-user px-4 py-3 text-[15px] leading-[1.75] text-ink sm:max-w-[82%]">
        {visible.objects.length > 0 && <div aria-label="本条消息引用的对象" className="mb-2.5 flex flex-wrap gap-1.5">
          {visible.objects.map((label,index) => <span key={index} className="rounded-md border border-jade-300/65 bg-panel/70 px-2 py-0.5 text-[11px] font-medium text-jade-800">{label}</span>)}
        </div>}
        {visible.text}
      </div>
    </div>
  }

  if (streaming && !message.content) {
    return <div className="rise-in py-1">
      <AgentWorkingIndicator />
    </div>
  }

  return <div className="rise-in group flex items-start gap-3">
    <PenguinArt pose="avatar" className="mt-0.5 size-9 shrink-0" />
    <div className="min-w-0 flex-1 pt-0.5">
      <div className="mb-2.5 flex items-center gap-2 text-[11px] text-muted">
        <span className="font-semibold tracking-[-0.01em] text-ink">企鹅助手</span>
        {streaming && <span role="status" className="inline-flex items-center gap-1.5 text-jade-700">
          <span aria-hidden="true" className="size-1.5 rounded-full bg-jade-500 agent-working-dot" />
          正在回复
        </span>}
      </div>
      {streaming ? (
        <p className="whitespace-pre-wrap break-words text-[15px] leading-[1.8] text-ink sm:text-base">
          {message.content}<span className="stream-caret" />
        </p>
      ) : <Markdown content={message.content} />}

      {!streaming && message.content && <div className="mt-3 flex min-h-8 items-center justify-start gap-2">
        <button type="button" onClick={() => void copyAnswer()}
          aria-label="复制回复" title="复制回复"
          className="inline-flex min-h-8 items-center gap-1.5 rounded-lg px-2 text-[11px] text-muted transition-colors hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700">
          {copyState === 'copied' ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
          {copyState === 'copied' ? '已复制' : '复制'}
        </button>
        {copyState === 'failed' && <span role="status" className="text-[11px] text-muted">复制失败，请手动选择文字</span>}
      </div>}
    </div>
  </div>
}
