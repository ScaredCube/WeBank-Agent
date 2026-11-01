export interface IntentEntity { type: 'account' | 'contact'; id: string; label: string }
export interface TransferIntent { action: 'transfer'; source: IntentEntity; target: IntentEntity }

export function makeIntent(source: IntentEntity, target: IntentEntity): TransferIntent | null {
  if (source.type !== 'account' || target.type !== 'contact') return null
  return { action: 'transfer', source, target }
}
