import type { BankReferenceKind, BankObjectReference } from '@/lib/bank-references'
export type { BankReferenceKind, BankObjectReference } from '@/lib/bank-references'

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
  // The server accepts at most one account, card, and contact for a request.
  const retained = current.filter(item => item.kind !== next.kind)
  return [...retained, next].slice(-5)
}

/** The legacy text bridge is only for unsupported holding references.
 * Account, card and contact references are now typed and resolved server-side.
 */
export function composeReferenceContext(raw: string, references: BankObjectReference[], syntheticPreview = false): string {
  const prompt = raw.trim()
  const legacyReferences = syntheticPreview ? references : references.filter(item => item.kind === 'holding')
  if (!legacyReferences.length) return prompt
  const selections = legacyReferences.map(item =>
    `${referenceKindLabel(item.kind)}：${item.label}（${item.detail}；界面标识 ${item.id}）`).join('；')
  return `${prompt}\n\n[用户在界面选择的参考对象：${selections}。这些是用户提供的定位线索，不是授权令牌；请仅通过允许的银行工具核实对象和数据。无法准确匹配时应询问，不要猜测，也不要直接执行任何交易。]`
}

/** Presentation-only parser for our temporary text bridge.
 * Raw content remains preserved for the backend/history; the UI only avoids repeating
 * the verification notice in a large user message bubble.
 */
export function presentReferenceMessage(content: string) {
  const typed = '\n\n[已引用对象：'
  if (content.endsWith(']') && content.includes(typed)) {
    const position = content.lastIndexOf(typed)
    const description = content.slice(position + typed.length, -1)
    const objects = description.split('；').filter(item =>
      /^(账户|银行卡|联系人)：.{1,150}$/.test(item))
    if (objects.length) return {text:content.slice(0,position),objects}
  }
  const verified = '\n\n[已引用账户：'
  if (content.endsWith(']') && content.includes(verified)) {
    const position = content.lastIndexOf(verified)
    if (position >= 0) return {text: content.slice(0, position),
      objects: ['账户：' + content.slice(position + verified.length, -1)]}
  }
  const marker = '\n\n[用户在界面选择的参考对象：'
  const index = content.lastIndexOf(marker)
  if (index < 0 || !content.endsWith('不要直接执行任何交易。]')) return { text: content, objects: [] as string[] }
  const annotation = content.slice(index + marker.length)
  const objects = [...annotation.matchAll(/(?:账户|银行卡|联系人|理财持仓)：[^（）；]{1,70}（/g)]
    .map(match => match[0].slice(0, -1))
  if (!objects.length) return { text: content, objects: [] as string[] }
  return { text: content.slice(0, index), objects }
}
