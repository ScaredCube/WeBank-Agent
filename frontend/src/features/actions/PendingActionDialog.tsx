import { useRef, useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { ApiError, type SubscriptionCancelExecution, type WealthOrderExecution } from '@/lib/api'
import type { StreamEvent } from '@/lib/sse'
import { formatCnyFen } from '@/lib/format'
import { serviceActionTransport, type ActionTransport } from './transport'

type ActionEvent = Extract<StreamEvent, { type: 'action_required' }>
type Stage = 'review' | 'code' | 'ready' | 'recover_execute' | 'complete' | 'cancelled' | 'unknown' | 'rejected' | 'recover_pending'

type Props = { event: ActionEvent; onClose: () => void; onFinish?: () => void; onResolved?: (status: 'completed' | 'cancelled' | 'expired') => void; open?: boolean; hidden?: boolean; onTogglePrivacy?: () => void; supplementalDescription?: string; verificationHint?: string } & ({ token: string; transport?: never } | { token?: never; transport: ActionTransport })

export function PendingActionDialog({ event, token, transport, onClose, onFinish = onClose, onResolved, open = true, hidden = false, onTogglePrivacy, supplementalDescription = '', verificationHint = '' }: Props) {
  const [stage, setStage] = useState<Stage>('review')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [code, setCode] = useState('')
  const [wealthResult, setWealthResult] = useState<WealthOrderExecution | null>(null)
  const [subscriptionResult, setSubscriptionResult] = useState<SubscriptionCancelExecution | null>(null)
  const busyRef = useRef(false)
  const { action, confirmation_token: confirmationToken } = event
  const service = transport ?? serviceActionTransport(token!)
  const transfer = action.action_type === 'transfer'
  const wealthSubscribe = action.action_type === 'wealth_subscribe'
  const wealthRedeem = action.action_type === 'wealth_redeem'
  const wealthOrder = wealthSubscribe || wealthRedeem
  const subscriptionCancel = action.action_type === 'subscription_cancel'
  const cardLoss = action.action_type === 'card_loss'
  const usesMoney = transfer || wealthOrder || subscriptionCancel
  const nonempty = (value: unknown): value is string => typeof value === 'string' && value.trim().length > 0
  const safeInteger = (value: unknown): value is number => Number.isSafeInteger(value)
  const positiveId = (value: unknown): value is number => safeInteger(value) && Number(value) > 0
  const validExpiry = Number.isFinite(Date.parse(action.expires_at))
  const validAmount = safeInteger(action.details.amount_fen) && Number(action.details.amount_fen) > 0
  const wealthOrderType = wealthSubscribe ? 'subscribe' : 'redeem'
  const missingBusinessTransport = (wealthOrder && !service.executeWealthOrder) ||
    (subscriptionCancel && !service.executeSubscriptionCancel)
  const supportedWealth = wealthOrder && action.risk_level === 'red' && event.order_id !== undefined && positiveId(event.order_id) &&
    action.details.order_type === wealthOrderType && positiveId(action.details.product_id) && nonempty(action.details.product_name) &&
    nonempty(action.details.product_category) && nonempty(action.details.product_risk_level) && safeInteger(action.details.expected_rate_bps) &&
    Number(action.details.expected_rate_bps) >= 0 && positiveId(action.details.term_days) && positiveId(action.details.account_id) &&
    nonempty(action.details.account_masked) && validAmount && action.details.currency === 'CNY'
  const supportedSubscription = subscriptionCancel && action.risk_level === 'yellow' && event.subscription_id !== undefined &&
    positiveId(event.subscription_id) && action.details.subscription_id === event.subscription_id && nonempty(action.details.merchant) &&
    validAmount && nonempty(action.details.cycle) && typeof action.details.next_charge_date === 'string' &&
    Number.isFinite(Date.parse(action.details.next_charge_date)) && action.details.status === 'active'
  const supported = !missingBusinessTransport && action.status === 'pending' && positiveId(action.id) && nonempty(confirmationToken) && validExpiry && (
    (transfer && (action.risk_level === 'yellow' || action.risk_level === 'red') && positiveId(event.transfer_id) && validAmount &&
      nonempty(action.details.account_masked) && nonempty(action.details.recipient_name) && action.details.currency === 'CNY') ||
    (cardLoss && action.risk_level === 'red' && positiveId(action.details.card_id) && nonempty(action.details.masked_number)) ||
    supportedWealth || supportedSubscription
  )
  const operationTitle = wealthSubscribe ? '确认模拟申购' : wealthRedeem ? '确认模拟赎回' : subscriptionCancel ? '确认取消订阅' :
    transfer ? '确认模拟转账' : cardLoss ? '确认模拟挂失' : '待确认操作'

  async function run(operation: () => Promise<void>, keepCodeOnRejection = false) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setMessage('')
    try { await operation() } catch (err) {
      if (err instanceof ApiError && err.status >= 400 && err.status < 500) {
        setMessage(err.message)
        if (!keepCodeOnRejection) setStage('rejected')
      } else {
        setStage('unknown')
        setMessage('请求结果暂不确定，请查询状态；不要重复发起操作。')
      }
    } finally { busyRef.current = false; setBusy(false) }
  }

  async function start() {
    if (!supported) return
    await run(async () => {
      if (action.risk_level === 'yellow') {
        const result = await service.step(action.id, 'confirm', { token: confirmationToken })
        if (result.status !== 'confirmed') throw new Error('确认状态无法核实')
        setStage('ready')
        setMessage(subscriptionCancel ? '已记录确认，订阅尚未取消。' : '已确认，操作尚未执行。')
      } else {
        const result = await service.step(action.id, 'verification/start', { token: confirmationToken })
        if (result.status !== 'pending') throw new Error('验证状态无法核实')
        setStage('code')
        setMessage('模拟验证已开始，操作尚未执行。')
      }
    })
  }

  async function verify() {
    await run(async () => {
      const result = await service.step(action.id, 'verification/verify', { token: confirmationToken, code })
      if (result.status !== 'verified') throw new Error('验证状态无法核实')
      setCode('')
      setStage('ready')
      setMessage('模拟验证通过，操作尚未执行。')
    }, true)
  }

  async function execute() {
    await run(async () => {
      if (transfer && event.transfer_id) {
        const result = await service.executeTransfer(event.transfer_id)
        if (result.status !== 'completed') throw new Error('执行结果无法确认')
        setMessage(result.message)
      } else if (cardLoss) {
        const result = await service.executeCardLoss(action.id)
        if (result.status !== 'lost') throw new Error('执行结果无法确认')
        setMessage('模拟卡片已挂失。')
      } else if (wealthOrder && event.order_id) {
        if (!service.executeWealthOrder) throw new ApiError('当前演示没有连接理财执行接口。', 422)
        const result = await service.executeWealthOrder(event.order_id)
        if (result.status !== 'completed' || result.order_id !== event.order_id || result.order_type !== wealthOrderType) {
          throw new Error('理财执行结果无法确认')
        }
        setWealthResult(result)
        setSubscriptionResult(null)
        setMessage(result.message)
      } else if (subscriptionCancel && event.subscription_id) {
        if (!service.executeSubscriptionCancel) throw new ApiError('当前演示没有连接订阅执行接口。', 422)
        const result = await service.executeSubscriptionCancel(action.id, event.subscription_id)
        if (result.status !== 'cancelled' || result.subscription_id !== event.subscription_id) {
          throw new Error('订阅取消结果无法确认')
        }
        setSubscriptionResult(result)
        setWealthResult(null)
        setMessage(result.message)
      } else throw new Error('不支持此操作')
      onResolved?.('completed')
      setStage('complete')
    })
  }

  async function cancel() {
    await run(async () => {
      const result = await service.step(action.id, 'cancel')
      if (result.status !== 'cancelled') throw new Error('取消状态无法核实')
      onResolved?.('cancelled')
      setStage('cancelled')
      setMessage(result.message)
    })
  }

  async function checkStatus() {
    await run(async () => {
      const result = await service.action(action.id)
      const labels: Record<string, string> = { pending: '待确认', confirmed: '已确认，尚需核实执行结果', verified: '已验证，尚需核实执行结果', completed: '已完成', cancelled: '已取消', expired: '已过期' }
      if (result.status === 'completed') {
        onResolved?.('completed')
        setWealthResult(null)
        setSubscriptionResult(null)
        setStage('complete')
        setMessage('服务端状态：已完成。服务端已记录此操作完成。')
      } else if (result.status === 'cancelled') {
        onResolved?.('cancelled')
        setStage('cancelled')
        setMessage('服务端状态：已取消。业务操作未执行。')
      } else if (result.status === 'expired') {
        onResolved?.('expired')
        setStage('cancelled')
        setMessage('服务端状态：已过期。业务操作未执行。')
      } else if (result.status === 'pending') {
        setStage('recover_pending')
        setMessage('服务端仍显示待确认。页面不会自动重试；你可以取消此动作，或关闭后等待其过期。')
      } else if ((wealthOrder && result.status === 'verified') ||
                 (subscriptionCancel && result.status === 'confirmed')) {
        if (Date.parse(action.expires_at) <= Date.now()) {
          setStage('unknown')
          setMessage('按本设备时间，此操作可能已过有效期。服务端尚未记录业务完成，请核对状态，不要重新发起操作。')
        } else {
          setStage('recover_execute')
          setMessage('服务端尚未记录业务完成。若要继续，可由你手动按原动作编号重试；页面不会自动重发。')
        }
      } else {
        setStage('unknown')
        setMessage(`服务端状态：${labels[result.status] ?? '未知'}。请先核对，不要重新发起新的操作。`)
      }
    })
  }

  const rows: [string, string][] = []
  const add = (label: string, value: unknown) => { if (typeof value === 'string' && value) rows.push([label, value]) }
  if (transfer) {
    add('账户', action.details.account_masked)
    add('收款人', action.details.recipient_name)
    add('收款号码', action.details.recipient_phone_masked)
  } else if (cardLoss) {
    add('账户', action.details.account_name)
    add('卡号', action.details.masked_number)
  } else if (wealthOrder) {
    add('产品', action.details.product_name)
    add('类别', action.details.product_category)
    add('产品风险等级', action.details.product_risk_level)
    if (safeInteger(action.details.expected_rate_bps)) {
      rows.push(['参考年化（不保证）', `${(action.details.expected_rate_bps / 100).toFixed(2)}%`])
    }
    if (positiveId(action.details.term_days)) rows.push(['期限', `${action.details.term_days} 天`])
    add('账户', action.details.account_masked)
  } else if (subscriptionCancel) {
    add('商户', action.details.merchant)
    const cycles: Record<string, string> = { weekly: '每周', monthly: '每月', quarterly: '每季度', yearly: '每年' }
    add('周期', typeof action.details.cycle === 'string' ? (cycles[action.details.cycle] ?? action.details.cycle) : undefined)
    add('下次扣费', action.details.next_charge_date)
    add('当前状态', action.details.status === 'active' ? '生效中' : action.details.status)
  }
  const amountLabel = wealthOrder ? '操作金额' : subscriptionCancel ? '单次扣费' : '金额'
  if (safeInteger(action.details.amount_fen)) rows.push([amountLabel, formatCnyFen(action.details.amount_fen)])
  add('备注', action.details.note)
  const privacyLabels = new Set(['金额', '操作金额', '单次扣费', '执行后余额', '该产品持仓'])
  const operationDescription = action.risk_level === 'red'
    ? '这是模拟业务。模拟验证码仅用于演示，不是真实银行身份验证；验证通过后仍需单独执行。'
    : subscriptionCancel
      ? '这是模拟订阅取消。确认只记录你的同意，只有服务端执行成功后订阅状态才会变更。'
      : '请核对信息。确认后操作仍需单独执行。'
  const executionLabel = wealthSubscribe ? '执行模拟申购' : wealthRedeem ? '执行模拟赎回' : subscriptionCancel ? '执行模拟取消' : '执行操作'

  return <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen && !busy) { if (stage === 'complete' || stage === 'cancelled') onFinish(); else onClose() } }}>
    <DialogContent className="p-6">
      <DialogTitle>{operationTitle}</DialogTitle>
      <DialogDescription className="mt-2">{supplementalDescription}{operationDescription}{action.risk_level === 'red' && verificationHint}</DialogDescription>
      <dl className="mt-5 divide-y divide-line rounded-xl border border-line px-4">{rows.map(([label, value]) => <div className="flex justify-between gap-4 py-3 text-sm" key={label}><dt className="text-muted">{label}</dt><dd className="text-right font-medium break-all">{privacyLabels.has(label) && hidden ? <span aria-label={`${label}已隐藏`}>••••</span> : value}</dd></div>)}</dl>
      {hidden && usesMoney && onTogglePrivacy && <button type="button" onClick={onTogglePrivacy} className="mt-3 text-sm text-jade-700 underline">查看金额</button>}
      {wealthResult && <dl className="mt-4 divide-y divide-line rounded-xl border border-jade-200 bg-jade-50/50 px-4" aria-label="理财执行结果">
        <div className="flex justify-between gap-4 py-3 text-sm"><dt className="text-muted">交易流水</dt><dd className="text-right font-medium">{wealthResult.transaction_id}</dd></div>
        <div className="flex justify-between gap-4 py-3 text-sm"><dt className="text-muted">执行后余额</dt><dd className="text-right font-medium">{hidden ? <span aria-label="余额已隐藏">••••</span> : formatCnyFen(wealthResult.balance_fen)}</dd></div>
        <div className="flex justify-between gap-4 py-3 text-sm"><dt className="text-muted">该产品持仓</dt><dd className="text-right font-medium">{hidden ? <span aria-label="持仓金额已隐藏">••••</span> : formatCnyFen(wealthResult.holding_fen)}</dd></div>
      </dl>}
      {subscriptionResult && <p className="mt-4 rounded-xl border border-jade-200 bg-jade-50/50 px-4 py-3 text-sm" role="status">服务端已确认模拟订阅 #{subscriptionResult.subscription_id} 已取消。</p>}
      <p className="mt-3 text-xs text-muted">有效期至 {new Date(action.expires_at).toLocaleString('zh-CN')}。关闭页面后确认凭证无法恢复。</p>
      {!supported && <p role="alert" className="mt-3 text-sm text-red-700">{missingBusinessTransport ? '当前演示没有连接此业务接口，无法继续。' : '动作信息不完整或当前不支持，请勿继续。'}</p>}
      {message && <p role="status" className="mt-3 text-sm text-ink">{message}</p>}
      {(stage === 'unknown' || stage === 'rejected') && <p className="mt-2 text-xs text-muted">移除本地记录不会取消服务端操作，也无法恢复确认凭证。</p>}
      {stage === 'code' && <label className="mt-4 block text-sm">模拟验证码<input value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" inputMode="numeric" className="mt-2 w-full rounded-xl border border-line bg-white px-3 py-2" /></label>}
      <div className="mt-5 flex flex-wrap gap-2">
        {(stage === 'review' || stage === 'code' || stage === 'recover_pending') && <button disabled={busy} onClick={() => void cancel()} className="flex-1 rounded-xl border border-line px-4 py-3 text-sm disabled:opacity-50">取消操作</button>}
        {stage === 'review' && <button disabled={busy || !supported || (hidden && usesMoney)} onClick={() => void start()} className="flex-1 rounded-xl bg-jade-700 px-4 py-3 text-sm text-white disabled:opacity-50">{action.risk_level === 'red' ? '开始模拟验证' : subscriptionCancel ? '确认取消' : '确认'}</button>}
        {stage === 'code' && <button disabled={busy || !code.trim()} onClick={() => void verify()} className="flex-1 rounded-xl bg-jade-700 px-4 py-3 text-sm text-white disabled:opacity-50">验证</button>}
        {(stage === 'ready' || stage === 'recover_execute') && <button disabled={busy || (hidden && usesMoney)} onClick={() => void execute()} className="flex-1 rounded-xl bg-jade-700 px-4 py-3 text-sm text-white disabled:opacity-50">{stage === 'recover_execute' ? '按原动作编号重试' : executionLabel}</button>}
        {(stage === 'unknown' || stage === 'rejected' || stage === 'recover_execute') && <button disabled={busy} onClick={() => void checkStatus()} className="flex-1 rounded-xl border border-line px-4 py-3 text-sm disabled:opacity-50">查询服务端状态</button>}
        {(stage === 'unknown' || stage === 'rejected') && <button disabled={busy} onClick={onFinish} className="flex-1 rounded-xl border border-line px-4 py-3 text-sm disabled:opacity-50">移除本地记录</button>}
        {(stage === 'complete' || stage === 'cancelled') && <button onClick={onFinish} className="flex-1 rounded-xl bg-jade-700 px-4 py-3 text-sm text-white">关闭</button>}
      </div>
    </DialogContent>
  </Dialog>
}
