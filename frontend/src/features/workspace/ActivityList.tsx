import { useMemo, useState } from 'react'
import { Activity, ArrowUpRight, CheckCircle2, Clock3, ShieldCheck, Search, XCircle } from 'lucide-react'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import type { AuditEntry } from '@/lib/api'

const eventNames: Record<string, string> = {
  demo_account_created: '创建模拟账户', risk_assessed: '风险检查', action_confirmed: '确认操作', action_confirm_denied: '确认被拒绝',
  action_cancelled: '取消操作', action_cancel_denied: '取消被拒绝',
  transfer_prepared: '准备转账', transfer_prepare_retried: '核对转账准备', transfer_prepare_denied: '转账准备被拒绝', transfer_prepare_failed: '转账准备失败',
  transfer_completed: '模拟转账完成', transfer_retried: '核对转账结果', transfer_denied: '转账被拒绝', transfer_failed: '转账失败',
  verification_started: '启动模拟验证', verification_succeeded: '模拟验证通过', verification_failed: '模拟验证失败', verification_locked: '模拟验证锁定',
  verification_denied: '模拟验证被拒绝', verification_start_denied: '无法启动验证', verification_start_failed: '验证启动失败', verification_error: '模拟验证异常',
  card_loss_prepared: '准备挂失', card_loss_completed: '模拟挂失完成', card_loss_denied: '挂失被拒绝', card_loss_failed: '挂失失败',
  wealth_order_prepared: '理财操作已准备', wealth_order_prepare_retried: '核对理财准备',
  wealth_order_prepare_denied: '理财准备未通过', wealth_order_prepare_failed: '理财操作准备失败',
  wealth_order_completed: '模拟理财操作已完成', wealth_order_retried: '核对理财操作',
  wealth_order_denied: '理财操作未执行', wealth_order_failed: '理财操作失败', wealth_risk_assessed: '理财风险检查',
  subscription_cancel_prepared: '取消订阅已准备', subscription_cancel_prepare_denied: '取消订阅准备未通过',
  subscription_cancel_prepare_failed: '取消订阅准备失败', subscription_cancelled: '模拟订阅已取消',
  subscription_cancel_retried: '核对订阅取消', subscription_cancel_denied: '取消订阅未执行',
  subscription_cancel_failed: '取消订阅失败',
  token_resolved: '使用数据引用', token_resolve_denied: '数据引用无效', token_revoked: '撤销数据引用',
}
const toolNames: Record<string, string> = {
  get_account_balance: '查询余额', list_recent_transactions: '查询交易记录', get_monthly_bill: '查询月度账单', calculate: '计算',
  prepare_transfer: '准备转账', transfer: '转账', get_card_status: '查询银行卡状态', prepare_card_loss: '准备挂失', card_loss: '挂失',
  get_wealth_products: '查询理财产品', get_wealth_holdings: '查询理财持仓', get_wealth_risk_profile: '查询理财风险测评',
  prepare_wealth_subscribe: '准备理财申购', prepare_wealth_redeem: '准备理财赎回', wealth_subscribe: '理财申购', wealth_redeem: '理财赎回',
  get_subscriptions: '查询订阅', detect_subscriptions: '识别订阅', prepare_cancel_subscription: '准备取消订阅', subscription_cancel: '取消订阅',
}
const resultNames: Record<string, string> = { success: '成功', denied: '未通过', failed: '失败', retry: '已核对', locked: '已锁定' }
function nameOf(entry: AuditEntry) {
  const wealthName = entry.tool === 'prepare_wealth_subscribe' || entry.tool === 'wealth_subscribe'
    ? '理财申购' : entry.tool === 'prepare_wealth_redeem' || entry.tool === 'wealth_redeem' ? '理财赎回' : null
  if (entry.event_type === 'wealth_order_prepared' && wealthName) return wealthName + '已准备'
  if (entry.event_type === 'wealth_order_completed' && wealthName) return '模拟' + wealthName + '已完成'
  if (entry.event_type === 'tool_called' || entry.event_type === 'tool_result') {
    const label = entry.tool ? toolNames[entry.tool] : undefined
    return label ? `${label}${entry.event_type === 'tool_result' ? '结果' : ''}` : entry.event_type === 'tool_result' ? '工具结果' : '工具调用'
  }
  return eventNames[entry.event_type] ?? '操作记录'
}
function kindOf(entry: AuditEntry) {
  if (entry.event_type === 'demo_account_created') return 'operations'
  if (entry.event_type.startsWith('tool_') || entry.event_type.startsWith('guard_')) return 'agent'
  if (entry.event_type.includes('transfer') || entry.event_type.includes('action_') || entry.event_type.includes('verification') || entry.event_type.includes('card_loss') || entry.event_type.includes('wealth_') || entry.event_type.includes('subscription_')) return 'operations'
  return 'security'
}
function dateKey(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '未知日期' : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}
function timeOf(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function ActivityList({ entries }: { entries: AuditEntry[] }) {
  const [keyword, setKeyword] = useState('')
  const [type, setType] = useState('all')
  const [status, setStatus] = useState('all')
  const matching = useMemo(() => entries.filter(item =>
    (type === 'all' || kindOf(item) === type) &&
    (status === 'all' || (status === 'success' ? item.result === 'success' : item.result !== 'success')) &&
    (!keyword.trim() || `${nameOf(item)} ${item.tool ?? ''} ${item.conversation_id ?? ''}`.toLowerCase().includes(keyword.trim().toLowerCase()))
  ), [entries, keyword, type, status])
  const groups = useMemo(() => {
    const byDate = new Map<string, AuditEntry[]>()
    for (const item of matching) {
      const key = dateKey(item.created_at)
      byDate.set(key, [...(byDate.get(key) ?? []), item])
    }
    return [...byDate.entries()]
  }, [matching])
  if (!entries.length) return <div className="mt-8"><MascotEmptyState title="还没有操作记录" description="查询、确认和金融事务将在这里留下可核对的记录。" pose="sleep" /></div>
  return <section aria-label="操作流水" className="space-y-6">
    <div className="flex flex-col gap-3 sm:flex-row">
      <label className="flex min-h-11 min-w-0 flex-1 items-center gap-2 rounded-xl border border-line bg-panel px-3 text-muted">
        <Search size={17} aria-hidden="true"/>
        <span className="sr-only">搜索已加载操作</span>
        <input value={keyword} onChange={e=>setKeyword(e.target.value)} placeholder="搜索已加载的操作" className="min-w-0 w-full bg-transparent text-sm text-ink outline-none placeholder:text-muted"/>
      </label>
      <select aria-label="操作类型" value={type} onChange={e=>setType(e.target.value)} className="min-h-11 rounded-xl border border-line bg-panel px-3 text-sm text-ink">
        <option value="all">全部类型</option><option value="agent">Agent 工具</option><option value="operations">金融操作</option><option value="security">安全记录</option>
      </select>
      <select aria-label="操作结果" value={status} onChange={e=>setStatus(e.target.value)} className="min-h-11 rounded-xl border border-line bg-panel px-3 text-sm text-ink">
        <option value="all">全部结果</option><option value="success">成功</option><option value="other">其他</option>
      </select>
    </div>
    {groups.length === 0 && <p role="status" className="rounded-2xl bg-panel p-6 text-sm text-muted">没有符合条件的已加载记录。</p>}
    {groups.map(([day, rows]) => <section key={day} className="space-y-3">
      <h3 className="flex items-baseline gap-3 text-base font-semibold tracking-tight text-ink">{day}<span className="text-xs font-normal text-muted">{rows.length} 条</span></h3>
      <ol className="grid gap-3">{rows.map(item => {
        const kind = kindOf(item)
        const ok = item.result === 'success'
        const Icon = kind === 'agent' ? Activity : kind === 'security' ? ShieldCheck : ok ? CheckCircle2 : XCircle
        return <li key={item.id}>
          <details className="group overflow-hidden rounded-2xl border border-line bg-panel transition-colors hover:border-jade-300">
            <summary className="flex cursor-pointer list-none items-start gap-3 px-4 py-4 focus-visible:outline-2 focus-visible:outline-jade-700 sm:px-5">
              <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-jade-50 text-jade-800"><Icon size={19}/></span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-ink">{nameOf(item)}</span>
                <span className="mt-1 block text-xs text-muted">{kind === 'agent' ? '小We · Agent 工具' : '模拟银行 · 服务端记录'}{item.conversation_id ? ` · 会话 #${item.conversation_id}` : ''}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1.5 text-xs text-muted">
                <span className="inline-flex items-center gap-1"><Clock3 size={12}/><time dateTime={item.created_at}>{timeOf(item.created_at)}</time></span>
                <span className={`rounded-full px-2 py-0.5 font-medium ${ok ? 'bg-jade-50 text-jade-800' : 'bg-slate-100 text-muted'}`}>{resultNames[item.result ?? ''] ?? '状态未知'}</span>
              </span>
              <ArrowUpRight size={16} aria-hidden="true" className="mt-1 shrink-0 text-muted transition group-open:rotate-90"/>
            </summary>
            <dl className="grid gap-2 border-t border-line bg-canvas/50 px-5 py-4 text-xs sm:grid-cols-2">
              <div><dt className="text-muted">记录时间</dt><dd className="mt-1 text-ink">{new Date(item.created_at).toLocaleString('zh-CN')}</dd></div>
              <div><dt className="text-muted">记录来源</dt><dd className="mt-1 text-ink">{kind === 'agent' ? 'Agent 工具调用链' : '模拟银行服务端'}</dd></div>
              {item.tool && <div><dt className="text-muted">工具</dt><dd className="mt-1 break-all text-ink">{item.tool}</dd></div>}
              {item.action_id != null && <div><dt className="text-muted">动作编号</dt><dd className="mt-1 text-ink">动作 #{item.action_id}</dd></div>}
              {item.transfer_id != null && <div><dt className="text-muted">转账编号</dt><dd className="mt-1 text-ink">转账 #{item.transfer_id}</dd></div>}
              {item.transaction_id != null && <div><dt className="text-muted">交易编号</dt><dd className="mt-1 text-ink">#{item.transaction_id}</dd></div>}
              {item.conversation_id != null && <div><dt className="text-muted">会话编号</dt><dd className="mt-1 text-ink">会话 #{item.conversation_id}</dd></div>}
            </dl>
          </details>
        </li>
      })}</ol>
    </section>)}
    <p className="text-xs text-muted">筛选仅作用于已加载记录；此处为可追溯日志，不代表操作可撤销。</p>
  </section>
}
