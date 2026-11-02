export type AssetKind = 'account' | 'contact' | 'holding'
export type IntentAction =
  | 'transfer'
  | 'internal_transfer'
  | 'collect'
  | 'purchase'
  | 'redeem'
  | 'convert'

export interface IntentEntity {
  kind: AssetKind
  id: number
  label: string
  detail?: string
  disabled?: boolean
}

export interface AssetIntent {
  action: IntentAction
  source: IntentEntity
  target: IntentEntity
  label: string
  prefill: string
}

const ACTIONS: Partial<Record<`${AssetKind}:${AssetKind}`, IntentAction>> = {
  'account:account': 'internal_transfer',
  'account:contact': 'transfer',
  'contact:account': 'collect',
  'account:holding': 'purchase',
  'holding:account': 'redeem',
  'holding:holding': 'convert',
}

const PREFILL: Record<IntentAction, string> = {
  // Dragging identifies the business intent and objects, never the amount.
  // An invented amount could become an executable simulated bank operation.
  transfer: '转账金额：',
  internal_transfer: '转账金额：',
  collect: '收款金额：',
  purchase: '申购金额：',
  redeem: '赎回金额：',
  convert: '转换金额：',
}

const LABEL: Record<IntentAction, string> = {
  transfer: '转账',
  internal_transfer: '内部转账',
  collect: '收款',
  purchase: '申购',
  redeem: '赎回',
  convert: '转换',
}

/** Pure collision matrix. Unsupported combinations return null and never
 * create a local action or call the model. */
export function resolveIntent(source: IntentEntity, target: IntentEntity): AssetIntent | null {
  if (source.kind === target.kind && source.id === target.id) return null
  if (source.disabled || target.disabled) return null
  const action = ACTIONS[`${source.kind}:${target.kind}`]
  if (!action) return null
  return {
    action,
    source,
    target,
    label: `${LABEL[action]} · ${source.label} → ${target.label}`,
    prefill: PREFILL[action],
  }
}

export function actionLabel(action: IntentAction): string {
  return LABEL[action]
}
