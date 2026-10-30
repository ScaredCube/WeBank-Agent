import { ChevronDown, History } from 'lucide-react'
import type { AuditEntry } from '@/lib/api'

const eventNames: Record<string, string> = {
  risk_assessed: '风险检查', action_confirmed: '确认操作', action_confirm_denied: '确认被拒绝',
  action_cancelled: '取消操作', action_cancel_denied: '取消被拒绝',
  transfer_prepared: '转账已准备', transfer_prepare_retried: '重新准备转账', transfer_prepare_denied: '转账准备被拒绝', transfer_prepare_failed: '转账准备失败',
  transfer_completed: '模拟转账已完成', transfer_retried: '转账请求重试', transfer_denied: '转账被拒绝', transfer_failed: '转账失败',
  verification_started: '开始模拟验证', verification_succeeded: '模拟验证通过', verification_failed: '模拟验证失败', verification_locked: '模拟验证已锁定',
  verification_denied: '模拟验证被拒绝', verification_start_denied: '模拟验证启动被拒绝', verification_start_failed: '模拟验证启动失败', verification_error: '模拟验证异常',
  card_loss_prepared: '挂失已准备', card_loss_completed: '模拟挂失已完成', card_loss_denied: '挂失被拒绝', card_loss_failed: '挂失失败',
  token_resolved: '数据引用已使用', token_resolve_denied: '数据引用不可用', token_revoked: '数据引用已撤销',
}
const toolNames: Record<string, string> = { get_account_balance: '查询余额', list_recent_transactions: '查询交易记录', get_monthly_bill: '查询月度账单', prepare_transfer: '准备转账', transfer: '转账', get_card_status: '查询卡片状态', prepare_card_loss: '准备挂失', card_loss: '挂失' }
const resultNames: Record<string, string> = { success: '成功', denied: '未通过', failed: '失败', retry: '重试', locked: '已锁定' }

function activityName(entry: AuditEntry) {
  if (entry.event_type === 'tool_called' || entry.event_type === 'tool_result') {
    const name = entry.tool ? toolNames[entry.tool] : undefined
    return name ? `${name}${entry.event_type === 'tool_result' ? '结果' : ''}` : entry.event_type === 'tool_result' ? '工具结果' : '工具调用'
  }
  return eventNames[entry.event_type] ?? '操作记录'
}

export function ActivityList({ entries }: { entries: AuditEntry[] }) {
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
