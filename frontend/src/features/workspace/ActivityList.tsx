import { ChevronDown, History } from 'lucide-react'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import type { AuditEntry } from '@/lib/api'

const eventNames: Record<string, string> = {
  risk_assessed: '风险检查', action_confirmed: '确认操作', action_confirm_denied: '确认被拒绝',
  action_cancelled: '取消操作', action_cancel_denied: '取消被拒绝',
  transfer_prepared: '转账已准备', transfer_prepare_retried: '重新准备转账', transfer_prepare_denied: '转账准备被拒绝', transfer_prepare_failed: '转账准备失败',
  transfer_completed: '模拟转账已完成', transfer_retried: '转账请求重试', transfer_denied: '转账被拒绝', transfer_failed: '转账失败',
  verification_started: '开始模拟验证', verification_succeeded: '模拟验证通过', verification_failed: '模拟验证失败', verification_locked: '模拟验证已锁定',
  verification_denied: '模拟验证被拒绝', verification_start_denied: '模拟验证启动被拒绝', verification_start_failed: '模拟验证启动失败', verification_error: '模拟验证异常',
  card_loss_prepared: '挂失已准备', card_loss_completed: '模拟挂失已完成', card_loss_denied: '挂失被拒绝', card_loss_failed: '挂失失败',
  wealth_order_prepared: '理财操作已准备', wealth_order_prepare_retried: '理财准备已复用',
  wealth_order_prepare_denied: '理财操作准备未通过', wealth_order_prepare_failed: '理财操作准备失败',
  wealth_order_completed: '模拟理财操作已完成', wealth_order_retried: '理财操作结果已核对',
  wealth_order_denied: '理财操作未执行', wealth_order_failed: '理财操作失败', wealth_risk_assessed: '理财风险检查',
  subscription_cancel_prepared: '取消订阅已准备', subscription_cancel_prepare_denied: '取消订阅准备未通过',
  subscription_cancel_prepare_failed: '取消订阅准备失败', subscription_cancelled: '模拟订阅已取消',
  subscription_cancel_retried: '取消订阅结果已核对', subscription_cancel_denied: '取消订阅未执行',
  subscription_cancel_failed: '取消订阅失败',
  token_resolved: '数据引用已使用', token_resolve_denied: '数据引用不可用', token_revoked: '数据引用已撤销',
}
const toolNames: Record<string, string> = {
  get_account_balance: '查询余额', list_recent_transactions: '查询交易记录', get_monthly_bill: '查询月度账单', calculate: '计算',
  prepare_transfer: '准备转账', transfer: '转账', get_card_status: '查询卡片状态', prepare_card_loss: '准备挂失', card_loss: '挂失',
  get_wealth_products: '查询理财产品', get_wealth_holdings: '查询理财持仓', get_wealth_risk_profile: '查询理财风险测评',
  prepare_wealth_subscribe: '准备理财申购', prepare_wealth_redeem: '准备理财赎回', wealth_subscribe: '理财申购', wealth_redeem: '理财赎回',
  get_subscriptions: '查询订阅', detect_subscriptions: '识别订阅', prepare_cancel_subscription: '准备取消订阅', subscription_cancel: '取消订阅',
}
const wealthOrderNames: Record<string, string> = {
  prepare_wealth_subscribe: '理财申购', prepare_wealth_redeem: '理财赎回',
  wealth_subscribe: '理财申购', wealth_redeem: '理财赎回',
}
const resultNames: Record<string, string> = { success: '成功', denied: '未通过', failed: '失败', retry: '重试', locked: '已锁定' }

function activityName(entry: AuditEntry) {
  if (entry.event_type === 'tool_called' || entry.event_type === 'tool_result') {
    const name = entry.tool ? toolNames[entry.tool] : undefined
    return name ? `${name}${entry.event_type === 'tool_result' ? '结果' : ''}` : entry.event_type === 'tool_result' ? '工具结果' : '工具调用'
  }
  const orderName = entry.tool ? wealthOrderNames[entry.tool] : undefined
  if (orderName && entry.event_type === 'wealth_order_prepared') return `${orderName}已准备`
  if (orderName && entry.event_type === 'wealth_order_completed') return `模拟${orderName}已完成`
  if (orderName && entry.event_type === 'wealth_order_retried') return `${orderName}结果已核对`
  return eventNames[entry.event_type] ?? '操作记录'
}

export function ActivityList({ entries }: { entries: AuditEntry[] }) {
  if (entries.length === 0) return <MascotEmptyState title="还没有操作记录" description="未来的操作轨迹会显示在这里。" pose="sleep" />
  return <ol className="space-y-1">{entries.map((entry) => <li key={entry.id} className="border-b border-line py-4">
    <details className="group">
      <summary className="flex cursor-pointer list-none gap-3 rounded focus-visible:outline-2 focus-visible:outline-jade-700">
        <History size={17} className="mt-0.5 shrink-0 text-jade-700" />
        <span className="min-w-0 flex-1"><span className="block text-sm font-medium">{activityName(entry)}</span><time className="mt-1 block text-xs text-muted">{new Date(entry.created_at).toLocaleString('zh-CN')}</time></span>
        <span className="text-xs text-muted">{entry.result ? resultNames[entry.result] ?? '状态未知' : ''}</span>
        <ChevronDown size={16} aria-hidden="true" className="shrink-0 text-muted group-open:rotate-180" />
      </summary>
      <div className="ml-7 mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted">
        {entry.conversation_id != null && <span>会话 #{entry.conversation_id}</span>}{entry.action_id != null && <span>动作 #{entry.action_id}</span>}{entry.transfer_id != null && <span>转账 #{entry.transfer_id}</span>}{entry.transaction_id != null && <span>交易 #{entry.transaction_id}</span>}
        {entry.conversation_id == null && entry.action_id == null && entry.transfer_id == null && entry.transaction_id == null && <span>暂无关联信息</span>}
      </div>
    </details>
  </li>)}</ol>
}
