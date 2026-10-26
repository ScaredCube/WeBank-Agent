import { ApiError, api, type Message } from '@/lib/api'

export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; message: Message | null }
  | { type: 'error'; message: string }
  | { type: 'action_required'; tool_calls: unknown[] }

interface StreamChatOptions {
  token: string
  conversationId: number
  content: string
  signal?: AbortSignal
  onEvent: (event: StreamEvent) => void
}

function parseBlock(block: string): StreamEvent | null {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data) return null

  try {
    return JSON.parse(data) as StreamEvent
  } catch {
    return null
  }
}

export async function streamChat({
  token,
  conversationId,
  content,
  signal,
  onEvent,
}: StreamChatOptions) {
  const response = await fetch(
    `${api.base}/chat/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ content }),
      signal,
    },
  )

  if (!response.ok) {
    let detail = '消息发送失败，请稍后再试'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep the default detail
    }
    throw new ApiError(detail, response.status)
  }

  if (!response.body) {
    throw new ApiError('浏览器不支持流式响应', 0)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    for (const block of blocks) {
      const event = parseBlock(block)
      if (event) onEvent(event)
    }
  }

  buffer += decoder.decode()
  const tail = parseBlock(buffer)
  if (tail) onEvent(tail)
}
