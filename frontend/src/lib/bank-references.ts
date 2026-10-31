/** Pure types shared by the chat transport and bank-object interactions. */
export type BankReferenceKind = 'account' | 'card' | 'contact' | 'holding'

export interface BankObjectReference {
  kind: BankReferenceKind
  id: number
  label: string
  detail: string
}
