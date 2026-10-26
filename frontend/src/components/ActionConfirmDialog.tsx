import { ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

export type RiskLevel = 'green' | 'yellow' | 'red'

export interface ActionDetail {
  title: string
  description: string
  risk: RiskLevel
  rows: { label: string; value: string }[]
  confirmText: string
}

const RISK_STYLES: Record<
  RiskLevel,
  { label: string; badge: string; icon: string }
> = {
  green: {
    label: '低风险',
    badge: 'border-jade-200 bg-jade-50 text-jade-700',
    icon: 'bg-jade-50 text-jade-700',
  },
  yellow: {
    label: '需确认',
    badge: 'border-amber-200 bg-amber-50 text-amber-700',
    icon: 'bg-amber-50 text-amber-600',
  },
  red: {
    label: '强验证',
    badge: 'border-red-200 bg-red-50 text-red-600',
    icon: 'bg-red-50 text-red-600',
  },
}

const DEMO_ACTION: ActionDetail = {
  title: '确认转账',
  description: '核对以下信息，确认后将立即提交。',
  risk: 'yellow',
  rows: [
    { label: '收款人', value: '陈晓' },
    { label: '金额', value: '¥268.00' },
    { label: '到账时间', value: '实时' },
  ],
  confirmText: '确认转账',
}

interface ActionConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  action?: ActionDetail
  onConfirm?: () => void
}

export function ActionConfirmDialog({
  open,
  onOpenChange,
  action = DEMO_ACTION,
  onConfirm,
}: ActionConfirmDialogProps) {
  const risk = RISK_STYLES[action.risk]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="p-0">
        <div className="px-6 pb-5 pt-6">
          <div className="flex items-start gap-3.5 pr-6">
            <div
              className={cn(
                'grid size-10 shrink-0 place-items-center rounded-xl',
                risk.icon,
              )}
            >
              <ShieldAlert className="size-5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <DialogTitle>{action.title}</DialogTitle>
                <span
                  className={cn(
                    'rounded-full border px-1.5 py-0.5 text-[10px] font-medium',
                    risk.badge,
                  )}
                >
                  {risk.label}
                </span>
              </div>
              <DialogDescription className="mt-1">
                {action.description}
              </DialogDescription>
            </div>
          </div>

          <div className="mt-5 divide-y divide-line/80 rounded-xl border border-line bg-canvas/60 px-4">
            {action.rows.map((row) => (
              <div
                key={row.label}
                className="flex items-center justify-between gap-6 py-2.5"
              >
                <span className="text-[12.5px] text-muted">{row.label}</span>
                <span className="text-right text-[13.5px] font-medium tabular-nums text-ink">
                  {row.value}
                </span>
              </div>
            ))}
          </div>

          <p className="mt-3 text-[11px] leading-relaxed text-muted/60">
            本次操作需由你本人确认，AI 无法代为确认。
          </p>
        </div>

        <div className="flex gap-2.5 border-t border-line/80 bg-canvas/50 px-6 py-4">
          <Button
            variant="outline"
            className="h-10 flex-1"
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            className="h-10 flex-1"
            onClick={() => {
              onConfirm?.()
              onOpenChange(false)
            }}
          >
            {action.confirmText}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
