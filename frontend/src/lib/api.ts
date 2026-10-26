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
}

export interface Health {
  status: string
  app: string
  llm: { mode: string; model: string }
}

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

  messages(token: string, conversationId: number) {
    return request<Message[]>(`/chat/conversations/${conversationId}/messages`, {}, token)
  },
}
