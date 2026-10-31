export type BankReferenceKind = 'account' | 'card' | 'contact' | 'holding'

export interface BankObjectReference {
  kind: BankReferenceKind
  id: number
  label: string
  detail: string
}

export const OBJECT_MIME = 'application/x-webank-object-reference'
const names: Record<BankReferenceKind, string> = {
  account: '账户', card: '银行卡', contact: '联系人', holding: '理财持仓',
}
export function referenceKindLabel(kind: BankReferenceKind) { return names[kind] }

export function parseBankReference(value: unknown): BankObjectReference | null {
  if (!value || typeof value !== 'object') return null
  const x = value as Record<string, unknown>
  if (typeof x.kind !== 'string' || !(x.kind in names) ||
    typeof x.id !== 'number' || !Number.isSafeInteger(x.id) || x.id <= 0 ||
    typeof x.label !== 'string' || typeof x.detail !== 'string' ||
    !x.label.trim() || x.label.length > 70 || x.detail.length > 90) return null
  return { kind: x.kind as BankReferenceKind, id: x.id, label: x.label.trim(), detail: x.detail.trim() }
}
export function parseDroppedReference(payload: string): BankObjectReference | null {
  if (!payload || payload.length > 1000) return null
  try { return parseBankReference(JSON.parse(payload)) } catch { return null }
}
export function addBankReference(current: BankObjectReference[], next: BankObjectReference): BankObjectReference[] {
  if (current.some(item => item.kind === next.kind && item.id === next.id)) return current
  return [...current, next].slice(0, 5)
}

/** Temporary text bridge until the server supports authenticated typed reference IDs.
 * The objects are NOT tokenized authority, and MUST be rechecked via backend tools.
 */
export function composeReferenceContext(raw: string, references: BankObjectReference[]): string {
  const prompt = raw.trim()
  if (!references.length) return prompt
  const selections = references.map(item =>
    `${referenceKindLabel(item.kind)}：${item.label}（${item.detail}；界面标识 ${item.id}）`).join('；')
  return `${prompt}\n\n[用户在界面选择的参考对象：${selections}。这些是用户提供的定位线索，不是授权令牌；请仅通过允许的银行工具核实对象和数据。无法准确匹配时应询问，不要猜测，也不要直接执行任何交易。]`
}

/** Presentation-only parser for our temporary text bridge.
 * Raw content remains preserved for the backend/history; the UI only avoids repeating
 * the verification notice in a large user message bubble.
 */
export function presentReferenceMessage(content: string) {
  const marker = '\n\n[用户在界面选择的参考对象：'
  const index = content.lastIndexOf(marker)
  if (index < 0 || !content.endsWith('不要直接执行任何交易。]')) return { text: content, objects: [] as string[] }
  const annotation = content.slice(index + marker.length)
  const objects = [...annotation.matchAll(/(?:账户|银行卡|联系人|理财持仓)：[^（）；]{1,70}（/g)]
    .map(match => match[0].slice(0, -1))
  if (!objects.length) return { text: content, objects: [] as string[] }
  return { text: content.slice(0, index), objects }
}
