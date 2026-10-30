import type { CardDescription } from '@/features/intelligent-ui/schema'
import { ApiError, type AuditEntry, type Conversation, type Message } from '@/lib/api'
import type { IntentEntity, TransferIntent } from '@/features/assets/intent'
import type { ActionTransport } from '@/features/actions/transport'
import type { StreamEvent } from '@/lib/sse'
import { formatCnyFen } from '@/lib/format'

const time = '2026-10-01T04:00:00Z'
const monthlyExpenseCategories = [
  { label: '餐饮', value: 86200 },
  { label: '日常', value: 71400 },
  { label: '出行', value: 41000 },
  { label: '其他', value: 40000 },
] as const
const monthlyExpenseFen = monthlyExpenseCategories.reduce((sum, category) => sum + category.value, 0)
const highestExpenseCategory = monthlyExpenseCategories.reduce((highest, category) => category.value > highest.value ? category : highest)
const monthlyIncomeFen = 520000
const cardStatusPreview = { account: '日常账户', lastFour: '8899', status: '正常' } as const

export const previewConversations: Conversation[] = [
  { id: 1, title: '日常财务', created_at: time, updated_at: time },
  { id: 2, title: '卡片与账户', created_at: time, updated_at: time },
  { id: 3, title: '收支比较', created_at: time, updated_at: time },
]
export const previewMessages: Record<number, Message[]> = {
  1: [{ id: 1, role: 'user', content: '帮我看看这个月的消费情况', created_at: time }, { id: 2, role: 'assistant', content: `本月支出共 ${formatCnyFen(monthlyExpenseFen)}，${highestExpenseCategory.label}金额最高，为 ${formatCnyFen(highestExpenseCategory.value)}。`, created_at: time }],
  2: [{ id: 3, role: 'user', content: '查看卡片状态', created_at: time }, { id: 4, role: 'assistant', content: `${cardStatusPreview.account}关联的银行卡（尾号 ${cardStatusPreview.lastFour}）状态${cardStatusPreview.status}。`, created_at: time }],
  3: [{ id: 5, role: 'user', content: '这段时间收入和支出分别是多少？', created_at: time }, { id: 6, role: 'assistant', content: `收入 ${formatCnyFen(monthlyIncomeFen)}，支出 ${formatCnyFen(monthlyExpenseFen)}，收入高出 ${formatCnyFen(monthlyIncomeFen - monthlyExpenseFen)}。`, created_at: time }],
}
export const previewCards: Record<number, CardDescription> = {
  1: { version: 1, id: 'preview-summary', title: '本月消费概览', source: '合成样例', observedAt: time, blocks: [{ type: 'metric', label: '支出', value: monthlyExpenseFen, unit: 'CNY_FEN' }, { type: 'bar_chart', title: '支出分类', rows: monthlyExpenseCategories.map(({ label, value }) => ({ label, value })) }, { type: 'list', rows: [{ label: '统计周期', value: '2026 年 10 月' }] }] },
  2: { version: 1, id: 'preview-card-status', title: '银行卡状态', source: '合成样例', observedAt: time, blocks: [{ type: 'list', rows: [{ label: '卡片', value: `${cardStatusPreview.account} · ${cardStatusPreview.lastFour}` }, { label: '状态', value: cardStatusPreview.status }] }, { type: 'action', action: 'open_assets' }] },
  3: { version: 1, id: 'preview-in-out', title: '收支比较', source: '合成样例', observedAt: time, blocks: [{ type: 'group', layout: 'columns', blocks: [{ type: 'metric', label: '收入', value: monthlyIncomeFen, unit: 'CNY_FEN' }, { type: 'metric', label: '支出', value: monthlyExpenseFen, unit: 'CNY_FEN' }] }] },
}
export const previewCardMessageIds: Record<number, number> = { 1: 2, 2: 4, 3: 6 }
export const previewActivity: AuditEntry[] = [{ id: 1, event_type: 'tool_called', tool: 'prepare_transfer', result: 'success', created_at: time, action_id: 12, conversation_id: 1 }]
export const previewAccounts: { entity: IntentEntity; masked: string; note: string }[] = [
  { entity: { type: 'account', id: 'preview-account', label: cardStatusPreview.account }, masked: `****${cardStatusPreview.lastFour}`, note: `样例卡片状态：${cardStatusPreview.status}` },
  { entity: { type: 'account', id: 'preview-reserve', label: '备用账户' }, masked: '****2631', note: '样例卡片状态：正常' },
]
export const previewContacts: { entity: IntentEntity; detail: string }[] = [
  { entity: { type: 'contact', id: 'preview-contact', label: '小林' }, detail: '合成联系人' },
  { entity: { type: 'contact', id: 'preview-contact-2', label: '小周' }, detail: '合成联系人' },
]
export function makePreviewAction(intent: TransferIntent): Extract<StreamEvent, { type: 'action_required' }> {
  const account = previewAccounts.find((item) => item.entity.id === intent.source.id)
  return {
    type: 'action_required', confirmation_token: 'synthetic-preview-only', transfer_id: 1,
    action: { id: 1, action_type: 'transfer', status: 'pending', risk_level: 'red', expires_at: '2035-01-01T00:00:00Z', details: { account_masked: account?.masked ?? '', recipient_name: intent.target.label, amount_fen: 5000, currency: 'CNY' } },
  }
}

export function createPreviewActionTransport(): ActionTransport {
  let status = 'pending'
  return {
    async step(_id, step, body) {
      if (step === 'cancel') status = 'cancelled'
      else if (step === 'confirm') status = 'confirmed'
      else if (step === 'verification/verify') {
        const code = body && 'code' in body ? body.code : undefined
        if (typeof code !== 'string' || !/^\d+$/.test(code)) throw new ApiError('样例请输入数字。', 400)
        status = 'verified'
      }
      return { status, message: '合成预览状态已更新。' }
    },
    async executeTransfer() { status = 'completed'; return { status, message: '合成预览：操作已模拟完成。' } },
    async executeCardLoss() { status = 'completed'; return { status: 'lost' } },
    async action() { return { status } },
  }
}
export const previewHoldings = [
  { name: '稳健组合', detail: '示例持仓', note: '这是合成持仓，不代表实际收益' },
  { name: '长期计划', detail: '示例持仓', note: '这是合成持仓，不代表实际收益' },
]
