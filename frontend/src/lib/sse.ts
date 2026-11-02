import { ApiError, api, type ChatViewContext, type Message } from '@/lib/api'
import { notifyUnauthorized } from '@/lib/session'
import type { BankObjectReference } from './bank-references'

export interface PendingAction {
  id: number
  action_type: string
  details: Record<string, unknown>
  risk_level: string
  status: string
  expires_at: string
}

export interface ChatIntentPayload {
  action: 'transfer' | 'internal_transfer' | 'collect' | 'purchase' | 'redeem' | 'convert'
  source: { kind: 'account' | 'contact' | 'holding'; id: number }
  target: { kind: 'account' | 'contact' | 'holding'; id: number }
}

export type StreamEvent =
  | { type: 'delta'; text: string }
  | { type: 'done'; message: Message | null }
  | { type: 'ui_status'; status: 'composing' | 'fallback' }
  | { type: 'ui_view'; view: unknown }
  | { type: 'subscription_result'; kind: 'subscriptions' | 'subscription_candidates'; data: unknown }
  | { type: 'bill_result'; data: unknown }
  | { type: 'card_result'; data: unknown }
  | { type: 'operation_result'; kind: 'internal_transfer'; data: unknown }
  | { type: 'error'; message: string }
  | { type: 'action_warning'; message: string }
  | {
      type: 'action_required'
      action: PendingAction
      confirmation_token: string
      transfer_id?: number
      order_id?: number
      subscription_id?: number
      collection_id?: number
      conversion_id?: number
    }

function isPositiveId(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) > 0
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function parseEvent(value: unknown): StreamEvent | null {
  if (!isRecord(value) || typeof value.type !== 'string') return null
  if (value.type === 'ui_status' && (value.status === 'composing' || value.status === 'fallback'))
    return { type: 'ui_status', status: value.status }
  if (value.type === 'ui_view' && Object.hasOwn(value, 'view'))
    return { type: 'ui_view', view: value.view }
  if (value.type === 'subscription_result' &&
      (value.kind === 'subscriptions' || value.kind === 'subscription_candidates') && Object.hasOwn(value, 'data'))
    return { type: 'subscription_result', kind: value.kind, data: value.data }
  if (value.type === 'bill_result' && isRecord(value.data)) return {type:'bill_result', data:value.data}
  if (value.type === 'card_result' && isRecord(value.data)) return {type:'card_result', data:value.data}
  if (value.type === 'operation_result' && value.kind === 'internal_transfer' && isRecord(value.data))
    return {type:'operation_result', kind:'internal_transfer', data:value.data}
  if (value.type === 'delta' && typeof value.text === 'string') return { type: 'delta', text: value.text }
  if (value.type === 'error' && typeof value.message === 'string') return { type: 'error', message: value.message }
  if (value.type === 'done') {
    if (value.message === null) return { type: 'done', message: null }
    const message = value.message
    if (isRecord(message) && typeof message.id === 'number' &&
        (message.role === 'user' || message.role === 'assistant' || message.role === 'system') &&
        typeof message.content === 'string' && typeof message.created_at === 'string') {
      return { type: 'done', message: message as unknown as Message }
    }
    return null
  }
  if (value.type === 'action_required' && isRecord(value.action) &&
      typeof value.confirmation_token === 'string' && value.confirmation_token.length > 0 &&
      isPositiveId(value.action.id) && typeof value.action.action_type === 'string' &&
      isRecord(value.action.details) && typeof value.action.risk_level === 'string' &&
      typeof value.action.status === 'string' && typeof value.action.expires_at === 'string' &&
      (value.transfer_id === undefined || isPositiveId(value.transfer_id)) &&
      (value.order_id === undefined || isPositiveId(value.order_id)) &&
      (value.subscription_id === undefined || isPositiveId(value.subscription_id)) &&
      (value.collection_id === undefined || isPositiveId(value.collection_id)) &&
      (value.conversion_id === undefined || isPositiveId(value.conversion_id))) {
    const actionType = value.action.action_type
    if ((actionType === 'transfer' && !isPositiveId(value.transfer_id)) ||
        (actionType === 'internal_transfer' && !isPositiveId(value.transfer_id)) ||
        (actionType === 'collection_request' && !isPositiveId(value.collection_id)) ||
        (actionType === 'wealth_convert' && !isPositiveId(value.conversion_id)) ||
        ((actionType === 'wealth_subscribe' || actionType === 'wealth_redeem') && !isPositiveId(value.order_id)) ||
        (actionType === 'subscription_cancel' && !isPositiveId(value.subscription_id))) return null
    return {
      type: 'action_required', action: value.action as unknown as PendingAction,
      confirmation_token: value.confirmation_token, transfer_id: value.transfer_id as number | undefined,
      order_id: value.order_id as number | undefined,
      subscription_id: value.subscription_id as number | undefined,
      collection_id: value.collection_id as number | undefined,
      conversion_id: value.conversion_id as number | undefined,
    }
  }
  return null
}

interface StreamChatOptions {
  token: string
  conversationId: number
  content: string
  references?: BankObjectReference[]
  intent?: ChatIntentPayload
  viewContext?: ChatViewContext
  requestId?: string
  signal?: AbortSignal
  onEvent: (event: StreamEvent) => void
}

function parseBlock(block: string): StreamEvent | 'invalid' | 'invalid_action' | null {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
    .join('\n')

  if (!data) return null

  try {
    const value: unknown = JSON.parse(data)
    const event = parseEvent(value)
    return event ?? (isRecord(value) && value.type === 'action_required' ? 'invalid_action' : 'invalid')
  } catch {
    return 'invalid'
  }
}

export async function streamChat({
  token,
  conversationId,
  content,
  references = [],
  intent,
  viewContext,
  requestId,
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
      // Only typed IDs cross the trust boundary; names and display labels are ignored.
      // The server validates ownership, state and card-to-account relationships.
      body: JSON.stringify({
        content,
        request_id: requestId,
        ...(viewContext ? { view_context: viewContext } : {}),
        ...(intent ? { intent } : {}),
        references: references
          .filter(ref => ref.kind === 'account' || ref.kind === 'card' || ref.kind === 'contact')
          .map(ref => ({ kind: ref.kind, id: ref.id })),
      }),
      signal,
    },
  )

  if (!response.ok) {
    if (response.status === 401) notifyUnauthorized(token)
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
  let terminal = false
  let warned = false
  let actionWarned = false

  function dispatch(block: string) {
    if (terminal) return
    const event = parseBlock(block)
    if (event === 'invalid_action') {
      if (!actionWarned) onEvent({ type: 'action_warning', message: '动作信息无法读取，服务端可能已创建操作。请先查看操作记录，不要重复发起。' })
      actionWarned = true
    } else if (event === 'invalid') {
      if (!warned) onEvent({ type: 'error', message: '收到异常事件，部分内容可能无法展示。' })
      warned = true
    } else if (event) {
      if (event.type === 'done' || event.type === 'error') terminal = true
      onEvent(event)
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        dispatch(block)
        if (terminal) break
      }
      if (terminal) {
        await reader.cancel().catch(() => {})
        buffer = ''
        break
      }
    }
    if (!terminal) {
      buffer += decoder.decode()
      dispatch(buffer)
    }
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError('连接中断，操作结果可能尚未确定，请先查看历史记录。', 0)
  } finally {
    reader.releaseLock()
  }
  if (!terminal) throw new ApiError('连接中断，操作结果可能尚未确定，请先查看历史记录。', 0)
}
