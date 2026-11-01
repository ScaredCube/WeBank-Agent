import { notifyUnauthorized } from './session'
import { z } from 'zod'

export interface User {
  id: number
  username: string
  display_name: string
}

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
  unavailable?: true
  /** Trusted tool result restored from a saved assistant message. */
  bill_result?: unknown | null
  card_result?: unknown | null
  tool_results?: unknown | null
}

export interface Health {
  status: string
  app: string
  llm: { mode: string; model: string }
}

export interface ChatSubmissionStatus {
  request_id: string
  state: 'processing' | 'completed' | 'action_pending' | 'interrupted' | 'failed'
  user_message_id: number | null
  pending_action_id: number | null
  message: Message | null
}

export interface BankCard {
  card_id: number
  account_name: string
  masked_number: string
  status: string
  account_status: string
}

export interface BankAccountOverview {
  account_id: number
  name: string
  masked_number: string
  currency: string
  balance_fen: number
  status: string
  card_status: string
  can_transfer: boolean
}

export interface BankContactOverview {
  contact_id: number
  name: string
  bank_name: string
  masked_phone: string
  status: string
  can_transfer: boolean
}

export interface WealthHoldingOverview {
  holding_id: number
  product_id: number
  product_name: string
  category: string
  risk_level: string
  expected_rate_bps: number
  amount_fen: number
  yesterday_earnings_fen: number
  status: string
}

export interface BankDashboardData {
  accounts: BankAccountOverview[]
  contacts: BankContactOverview[]
  holdings: WealthHoldingOverview[]
  risk_profile: { risk_level: string; score: number; assessed_at: string | null }
  generated_at: string
}

export interface AuditEntry {
  id: number
  event_type: string
  result: string | null
  created_at: string
  action_id: number | null
  conversation_id?: number | null
  transfer_id?: number | null
  transaction_id?: number | null
  tool?: string | null
}

export type ActionStatus = 'pending' | 'confirmed' | 'cancelled' | 'expired' | 'verified' | 'completed'

export interface WealthOrderExecution {
  order_id: number
  order_type: 'subscribe' | 'redeem'
  status: 'completed'
  transaction_id: number
  balance_fen: number
  holding_fen: number
  message: string
}

export interface SubscriptionCancelExecution {
  subscription_id: number
  status: 'cancelled'
  message: string
}

const positiveId = z.number().int().safe().positive()
const messageSchema = z.object({ id: positiveId, role: z.enum(['user', 'assistant', 'system']), content: z.string(), created_at: z.string(), bill_result: z.unknown().optional(), card_result: z.unknown().optional(), tool_results: z.unknown().optional() })
const submissionStatusSchema = z.object({
  request_id: z.string().min(8),
  state: z.enum(['processing', 'completed', 'action_pending', 'interrupted', 'failed']),
  user_message_id: positiveId.nullable(),
  pending_action_id: positiveId.nullable(),
  message: messageSchema.nullable(),
})
const cardListSchema = z.array(z.object({ card_id: positiveId, account_name: z.string(), masked_number: z.string(), status: z.string(), account_status: z.string() }))
const bankDashboardSchema = z.object({
  accounts: z.array(z.object({
    account_id: positiveId, name: z.string(), masked_number: z.string(), currency: z.string(),
    balance_fen: z.number().int().safe(), status: z.string(), card_status: z.string(), can_transfer: z.boolean(),
  })),
  contacts: z.array(z.object({
    contact_id: positiveId, name: z.string(), bank_name: z.string(), masked_phone: z.string(),
    status: z.string(), can_transfer: z.boolean(),
  })),
  holdings: z.array(z.object({
    holding_id: positiveId, product_id: positiveId, product_name: z.string(), category: z.string(),
    risk_level: z.string(), expected_rate_bps: z.number().int().safe(), amount_fen: z.number().int().safe(),
    yesterday_earnings_fen: z.number().int().safe(), status: z.string(),
  })),
  risk_profile: z.object({ risk_level: z.string(), score: z.number().int().safe(), assessed_at: z.string().nullable() }),
  generated_at: z.string().refine((value) => Number.isFinite(Date.parse(value))),
})
const auditListSchema = z.array(z.object({
  id: positiveId, event_type: z.string(), result: z.string().nullable(),
  created_at: z.string().refine((value) => Number.isFinite(Date.parse(value))),
  action_id: positiveId.nullable(), conversation_id: positiveId.nullable().optional(),
  transfer_id: positiveId.nullable().optional(), transaction_id: positiveId.nullable().optional(),
  tool: z.string().nullable().optional(),
}))
const actionStatusSchema = z.object({
  id: positiveId,
  action_type: z.string().min(1),
  status: z.enum(['pending', 'confirmed', 'cancelled', 'expired', 'verified', 'completed']),
  expires_at: z.string().refine((value) => Number.isFinite(Date.parse(value))),
})
const wealthOrderExecutionSchema = z.object({
  order_id: positiveId,
  order_type: z.enum(['subscribe', 'redeem']),
  status: z.literal('completed'),
  transaction_id: positiveId,
  balance_fen: z.number().int().safe().nonnegative(),
  holding_fen: z.number().int().safe().nonnegative(),
  message: z.string(),
})
const subscriptionCancelExecutionSchema = z.object({
  subscription_id: positiveId,
  status: z.literal('cancelled'),
  message: z.string(),
})

export interface LoginResponse {
  access_token: string
  token_type: string
  user: User
}

const API_BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}, token?: string | null): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    if (response.status === 401 && token) notifyUnauthorized(token)
    let detail = '请求失败，请稍后再试'
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      // keep the default detail
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

export const api = {
  base: API_BASE,

  login(username: string, password: string) {
    return request<LoginResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })
  },

  health() {
    return request<Health>('/health')
  },

  conversations(token: string) {
    return request<Conversation[]>('/chat/conversations', {}, token)
  },

  createConversation(token: string) {
    return request<Conversation>(
      '/chat/conversations',
      { method: 'POST', body: JSON.stringify({}) },
      token,
    )
  },

  renameConversation(token: string, conversationId: number, title: string) {
    return request<Conversation>(`/chat/conversations/${conversationId}`, {
      method: 'PATCH', body: JSON.stringify({ title }),
    }, token)
  },

  async submissionStatus(token: string, conversationId: number, requestId: string): Promise<ChatSubmissionStatus> {
    const raw = await request<unknown>(
      `/chat/conversations/${conversationId}/requests/${encodeURIComponent(requestId)}`, {}, token,
    )
    const result = submissionStatusSchema.safeParse(raw)
    if (!result.success) throw new Error('请求状态数据异常，请核对历史。')
    return result.data
  },

  async messages(token: string, conversationId: number): Promise<Message[]> {
    const data = await request<unknown>(`/chat/conversations/${conversationId}/messages`, {}, token)
    if (!Array.isArray(data)) throw new Error('历史消息数据格式异常，请稍后重试。')
    const seen = new Set<number>()
    return data.map((item, index) => {
      const parsed = messageSchema.safeParse(item)
      if (parsed.success && !seen.has(parsed.data.id)) { seen.add(parsed.data.id); return parsed.data }
      return { id: -(index + 1), role: 'system', content: '', created_at: '', unavailable: true }
    })
  },

  async cards(token: string): Promise<BankCard[]> {
    const data = cardListSchema.safeParse(await request<unknown>('/cards', {}, token))
    if (!data.success) throw new Error('银行卡数据格式异常，请稍后重试。')
    return data.data
  },

  async bankDashboard(token: string): Promise<BankDashboardData> {
    const data = bankDashboardSchema.safeParse(await request<unknown>('/bank/dashboard', {}, token))
    if (!data.success) throw new Error('账户与资产数据格式异常，请稍后重试。')
    return data.data
  },

  async createDemoAccount(token: string, name: string): Promise<BankAccountOverview> {
    const raw = await request<unknown>('/bank/accounts/demo', {
      method: 'POST', body: JSON.stringify({ name }),
    }, token)
    const parsed = bankDashboardSchema.shape.accounts.element.safeParse(raw)
    if (!parsed.success) throw new Error('新增账户结果格式异常，请刷新资产确认。')
    return parsed.data
  },

  prepareCardLoss(token: string, cardId: number, idempotencyKey: string) {
    return request<{ action_id: number; confirmation_token: string | null }>(`/cards/${cardId}/loss/prepare`, {
      method: 'POST', body: JSON.stringify({ idempotency_key: idempotencyKey }),
    }, token)
  },

  actionDetails(token: string, id: number) {
    return request<unknown>(`/actions/${id}`, {}, token)
  },

  monthlyBill(token: string, month?: string, accountId?: number) {
    const params = new URLSearchParams()
    if (month) params.set('month', month)
    if (accountId !== undefined) params.set('account_id', String(accountId))
    const query = params.toString()
    return request<unknown>(`/bills/monthly${query ? `?${query}` : ''}`, {}, token)
  },

  async audit(token: string, afterId = 0): Promise<AuditEntry[]> {
    const data = auditListSchema.safeParse(await request<unknown>(`/audit?limit=50&after_id=${afterId}`, {}, token))
    if (!data.success) throw new Error('操作记录数据格式异常，请稍后重试。')
    return data.data
  },

  action(token: string, id: number) {
    return request<unknown>(`/actions/${id}`, {}, token).then((result) => {
      const data = actionStatusSchema.safeParse(result)
      if (!data.success || data.data.id !== id) throw new Error('操作状态数据格式异常，请稍后重新查询。')
      return { status: data.data.status }
    })
  },

  actionStep(token: string, id: number, step: 'cancel' | 'confirm' | 'verification/start' | 'verification/verify', body?: object) {
    return request<{ status: string; message: string }>(`/actions/${id}/${step}`, {
      method: 'POST', ...(body ? { body: JSON.stringify(body) } : {}),
    }, token)
  },

  executeTransfer(token: string, id: number) {
    return request<{ status: string; message: string }>(`/transfers/${id}/execute`, { method: 'POST' }, token)
  },

  executeCardLoss(token: string, actionId: number) {
    return request<{ status: string }>(`/cards/loss/${actionId}/execute`, { method: 'POST' }, token)
  },

  async executeWealthOrder(token: string, orderId: number): Promise<WealthOrderExecution> {
    const result = wealthOrderExecutionSchema.safeParse(await request<unknown>(
      `/wealth/orders/${orderId}/execute`, { method: 'POST' }, token,
    ))
    if (!result.success || result.data.order_id !== orderId) {
      throw new Error('理财执行结果数据格式异常，请查询服务端状态。')
    }
    return result.data
  },

  async executeSubscriptionCancel(
    token: string, actionId: number, subscriptionId: number,
  ): Promise<SubscriptionCancelExecution> {
    const result = subscriptionCancelExecutionSchema.safeParse(await request<unknown>(
      `/subscriptions/cancel/${actionId}/execute`, { method: 'POST' }, token,
    ))
    if (!result.success || result.data.subscription_id !== subscriptionId) {
      throw new Error('订阅取消结果数据格式异常，请查询服务端状态。')
    }
    return result.data
  },
}
