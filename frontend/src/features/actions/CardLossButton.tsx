import { useRef, useState } from 'react'
import { z } from 'zod'

import { ApiError, api } from '@/lib/api'
import type { StreamEvent } from '@/lib/sse'

const preparedSchema = z.object({
  action_id: z.number().int().positive(),
  confirmation_token: z.string().min(1).nullable(),
})

const actionSchema = z.object({
  id: z.number().int().positive(),
  action_type: z.literal('card_loss'),
  status: z.enum(['pending', 'confirmed', 'verified', 'completed', 'cancelled', 'expired']),
  risk_level: z.literal('red'),
  expires_at: z.string().min(1),
  details: z.object({
    card_id: z.number().int().positive(),
    masked_number: z.string().min(1),
  }).passthrough(),
})

type ActionStatus = z.infer<typeof actionSchema>['status']
type UnresolvedStatus = Extract<ActionStatus, 'pending' | 'confirmed' | 'verified'> | 'unknown'

export type CardLossRecovery = {
  idempotencyKey: string
  status: UnresolvedStatus
  actionId?: number
}

function createIdempotencyKey() {
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(24))
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function describeStatus(status: UnresolvedStatus) {
  if (status === 'pending') return '已找到待处理的挂失申请。'
  if (status === 'confirmed') return '申请已确认，但一次性凭证无法恢复，因此不能继续验证或执行。请查看操作记录并等待状态结束。'
  if (status === 'verified') return '申请已验证，但一次性凭证无法恢复，因此不能继续执行。请查看操作记录并等待状态结束。'
  return '准备结果暂不确定，请核对申请状态后再决定下一步。'
}

type Props = {
  token: string
  cardId: number
  disabled: boolean
  onBusyChange: (busy: boolean) => void
  onPrepared: (event: Extract<StreamEvent, { type: 'action_required' }>) => void
  recovery?: CardLossRecovery | null
  onRecoveryChange?: (cardId: number, recovery: CardLossRecovery | null) => void
  onResolved?: (cardId: number, status: Extract<ActionStatus, 'completed' | 'cancelled' | 'expired'>) => void
}

export function CardLossButton({ token, cardId, disabled, onBusyChange, onPrepared, recovery, onRecoveryChange, onResolved }: Props) {
  const [localRecovery, setLocalRecovery] = useState<CardLossRecovery | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [messageRole, setMessageRole] = useState<'alert' | 'status'>('status')
  const [confirmationToken, setConfirmationToken] = useState<string | null>(null)
  const lock = useRef(false)
  const activeRecovery = recovery === undefined ? localRecovery : recovery

  function updateRecovery(next: CardLossRecovery | null) {
    setLocalRecovery(next)
    onRecoveryChange?.(cardId, next)
  }

  function showMessage(text: string, role: 'alert' | 'status' = 'status') {
    setMessage(text)
    setMessageRole(role)
  }

  function settle(status: Extract<ActionStatus, 'completed' | 'cancelled' | 'expired'>) {
    updateRecovery(null)
    setConfirmationToken(null)
    const text = status === 'completed'
      ? '服务端已记录挂失完成。'
      : status === 'cancelled'
        ? '挂失申请已取消，操作未执行。'
        : '挂失申请已过期，可以重新发起。'
    showMessage(text)
    onResolved?.(cardId, status)
  }

  async function inspectAction(actionId: number, key: string, credential: string | null): Promise<ActionStatus> {
    const parsed = actionSchema.safeParse(await api.actionDetails(token, actionId))
    if (!parsed.success) throw new Error('动作状态数据格式异常，暂时无法核对。')
    const action = parsed.data
    if (action.id !== actionId || action.details.card_id !== cardId) {
      throw new Error('查到的挂失申请与当前银行卡不匹配，已停止后续操作。')
    }

    if (action.status === 'completed' || action.status === 'cancelled' || action.status === 'expired') {
      settle(action.status)
      return action.status
    }

    const nextRecovery: CardLossRecovery = {
      idempotencyKey: key,
      actionId,
      status: action.status,
    }
    updateRecovery(nextRecovery)

    if (action.status === 'pending' && credential) {
      setConfirmationToken(null)
      showMessage('挂失申请已核实，可以继续查看确认步骤。')
      onPrepared({ type: 'action_required', action, confirmation_token: credential })
      return action.status
    }

    setConfirmationToken(credential)
    if (action.status === 'pending') {
      showMessage('已找到待处理申请，但首次响应中的一次性验证凭证无法恢复。你可以取消申请，或等待它过期；不能继续确认或执行。', 'alert')
    } else {
      showMessage(describeStatus(action.status), 'alert')
    }
    return action.status
  }

  async function prepareWithKey(key: string, isRecovery: boolean) {
    let response: z.infer<typeof preparedSchema>
    try {
      response = preparedSchema.parse(await api.prepareCardLoss(token, cardId, key))
    } catch (err) {
      if (!isRecovery && err instanceof ApiError && err.status >= 400 && err.status < 500) {
        updateRecovery(null)
        setConfirmationToken(null)
        showMessage(err.message, 'alert')
      } else {
        updateRecovery({ idempotencyKey: key, status: 'unknown' })
        showMessage(`准备结果暂不确定。${err instanceof Error ? err.message : '请核对申请状态后再决定下一步。'}`, 'alert')
      }
      return
    }

    const nextRecovery: CardLossRecovery = {
      idempotencyKey: key,
      actionId: response.action_id,
      status: 'unknown',
    }
    updateRecovery(nextRecovery)
    setConfirmationToken(response.confirmation_token)

    try {
      await inspectAction(response.action_id, key, response.confirmation_token)
    } catch (err) {
      showMessage(`已取得申请编号，但暂时无法读取其状态。${err instanceof Error ? err.message : '请稍后核对状态。'}`, 'alert')
    }
  }

  async function run(task: () => Promise<void>) {
    if (lock.current || disabled) return
    lock.current = true
    setBusy(true)
    onBusyChange(true)
    try {
      await task()
    } finally {
      lock.current = false
      setBusy(false)
      onBusyChange(false)
    }
  }

  async function start() {
    await run(async () => {
      let key: string
      try {
        key = createIdempotencyKey()
      } catch {
        showMessage('当前环境无法安全生成申请编号，暂不能准备挂失。', 'alert')
        return
      }
      setMessage('')
      updateRecovery({ idempotencyKey: key, status: 'unknown' })
      await prepareWithKey(key, false)
    })
  }

  async function checkRecovery() {
    if (!activeRecovery) return
    await run(async () => {
      setMessage('')
      if (activeRecovery.actionId) {
        try {
          await inspectAction(activeRecovery.actionId, activeRecovery.idempotencyKey, confirmationToken)
        } catch (err) {
          showMessage(`暂时无法读取申请状态。${err instanceof Error ? err.message : '请稍后重试查询。'}`, 'alert')
        }
      } else {
        await prepareWithKey(activeRecovery.idempotencyKey, true)
      }
    })
  }

  async function cancelPending() {
    if (!activeRecovery?.actionId || activeRecovery.status !== 'pending') return
    await run(async () => {
      setMessage('')
      try {
        const result = await api.actionStep(token, activeRecovery.actionId!, 'cancel')
        if (result.status === 'cancelled') {
          settle('cancelled')
          return
        }
        throw new Error('服务端没有确认取消结果。')
      } catch (err) {
        const cause = err instanceof Error ? err.message : '取消请求未能确认。'
        try {
          const status = await inspectAction(activeRecovery.actionId!, activeRecovery.idempotencyKey, null)
          if (status === 'pending') {
            showMessage(`取消结果未确认，服务端仍显示待处理。可以再次明确选择取消。${cause}`, 'alert')
          }
        } catch (queryError) {
          showMessage(`取消结果和申请状态都无法确认。请稍后查询，不要重新发起挂失。${cause} ${queryError instanceof Error ? queryError.message : ''}`, 'alert')
        }
      }
    })
  }

  const statusText = activeRecovery ? describeStatus(activeRecovery.status) : ''
  const recovering = activeRecovery !== null
  const canCancel = activeRecovery?.status === 'pending' && activeRecovery.actionId !== undefined

  return (
    <div className="mt-4">
      {!recovering && (
        <button type="button" disabled={disabled || busy} onClick={() => void start()} className="rounded-xl border border-line px-3 py-2 text-xs text-ink disabled:opacity-50">
          {busy ? '准备中…' : '模拟挂失'}
        </button>
      )}
      {recovering && (
        <div className="space-y-2">
          <p role={message ? messageRole : activeRecovery.status === 'unknown' ? 'alert' : 'status'} className="text-xs leading-5 text-red-700">
            {message || statusText}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy || disabled} onClick={() => void checkRecovery()} className="rounded-xl border border-line px-3 py-2 text-xs text-ink disabled:opacity-50">
              {busy ? '核对中…' : activeRecovery.actionId ? '核对申请状态' : '核对准备结果'}
            </button>
            {canCancel && (
              <button type="button" disabled={busy || disabled} onClick={() => void cancelPending()} className="rounded-xl border border-line px-3 py-2 text-xs text-ink disabled:opacity-50">
                {busy ? '处理中…' : '取消待处理申请'}
              </button>
            )}
          </div>
        </div>
      )}
      {!recovering && message && <p role={messageRole} className="mt-2 text-xs leading-5 text-red-700">{message}</p>}
    </div>
  )
}
