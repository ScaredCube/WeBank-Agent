/** Tab-scoped request-recovery hints. Never store text, bank data or tokens.
 * Every lookup is authorized again by the backend; there is NO automatic retry.
 */
const KEY = 'xiaowe:chat-inflight:v1'
const MAX_AGE_MS = 24 * 60 * 60 * 1000
const MAX_RECORDS = 12

export interface PendingChatRequest {
  conversationId: number
  requestId: string
  createdAt: number
}

function valid(value: unknown): value is PendingChatRequest {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<PendingChatRequest>
  return Number.isSafeInteger(item.conversationId) && Number(item.conversationId) > 0 &&
    typeof item.requestId === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(item.requestId) &&
    Number.isFinite(item.createdAt) &&
    Number(item.createdAt) <= Date.now() + 60_000 &&
    Date.now() - Number(item.createdAt) <= MAX_AGE_MS
}

export function readPendingChatRequests(): PendingChatRequest[] {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return []
    const value: unknown = JSON.parse(raw)
    if (!Array.isArray(value)) throw Error('invalid')
    const seen = new Set<string>()
    const validRecords = value.filter((item): item is PendingChatRequest => {
      if (!valid(item) || seen.has(item.requestId)) return false
      seen.add(item.requestId)
      return true
    }).slice(-MAX_RECORDS)
    if (validRecords.length !== value.length)
      sessionStorage.setItem(KEY, JSON.stringify(validRecords))
    return validRecords
  } catch {
    try { sessionStorage.removeItem(KEY) } catch { /* storage blocked */ }
    return []
  }
}

export function savePendingChatRequest(record: PendingChatRequest): void {
  if (!valid(record)) return
  try {
    const rest = readPendingChatRequests().filter(item => item.requestId !== record.requestId)
    sessionStorage.setItem(KEY, JSON.stringify([...rest, record].slice(-MAX_RECORDS)))
  } catch { /* private mode */ }
}

export function clearPendingChatRequest(requestId: string): void {
  try {
    const filtered = readPendingChatRequests().filter(item => item.requestId !== requestId)
    if (!filtered.length) sessionStorage.removeItem(KEY)
    else sessionStorage.setItem(KEY, JSON.stringify(filtered))
  } catch { /* private mode */ }
}
