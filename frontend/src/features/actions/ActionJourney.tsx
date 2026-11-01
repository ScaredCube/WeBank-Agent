import { AlertTriangle, Check, CircleDot, Info, type LucideIcon } from 'lucide-react'

/** Mirrors the verified local dialog state; it does not infer progress from elapsed time. */
export type ActionStage = 'review' | 'code' | 'ready' | 'recover_execute' | 'complete' |
  'cancelled' | 'unknown' | 'rejected' | 'recover_pending'

type Step = { label: string; number: number }
type JourneyState = {
  heading: string
  explanation: string
  active: number | null
  doneThrough: number
  caution: boolean
}

function resolveJourney(stage: ActionStage): JourneyState {
  const initial = { heading: '等待核对', explanation: '确认信息后才能继续，当前操作尚未执行。', active: 0, doneThrough: -1, caution: false }
  if (stage === 'review') return initial
  if (stage === 'code') return { heading: '等待模拟验证', explanation: '验证通过后将自动执行，无需再次点击。', active: 1, doneThrough: 0, caution: false }
  if (stage === 'ready') return { heading: '等待执行', explanation: '已通过确认或验证，银行业务尚未执行。', active: 2, doneThrough: 1, caution: false }
  if (stage === 'complete') return { heading: '服务端已确认完成', explanation: '服务端已返回并确认此操作完成。', active: 3, doneThrough: 3, caution: false }
  if (stage === 'recover_execute') return {
    heading: '继续执行需谨慎', explanation: '服务端仍未记录完成；仅可按原动作编号由你手动决定是否继续。', active: 2, doneThrough: 1, caution: true,
  }
  if (stage === 'recover_pending') return {
    heading: '服务端仍待确认', explanation: '此动作尚未完成。可选择取消，页面不会自行重新提交。', active: 0, doneThrough: -1, caution: true,
  }
  if (stage === 'cancelled') return {
    heading: '操作已终止', explanation: '服务端已确认取消或过期，业务操作没有执行。', active: null, doneThrough: -1, caution: false,
  }
  return {
    heading: stage === 'rejected' ? '请求被拒绝，待核实' : '执行结果尚不确定',
    explanation: '不要重复发起新的操作。请先查询服务端状态。',
    active: null, doneThrough: -1, caution: true,
  }
}

const steps = (needsVerification: boolean): Step[] => [
  { label: '核对信息', number: 1 },
  { label: needsVerification ? '模拟验证' : '确认意向', number: 2 },
  { label: '执行操作', number: 3 },
  { label: '查看结果', number: 4 },
]

export function ActionJourney({ stage, needsVerification, busy = false }: {
  stage: ActionStage
  needsVerification: boolean
  busy?: boolean
}) {
  const state = resolveJourney(stage)
  const items = steps(needsVerification)
  const StatusIcon: LucideIcon = state.caution ? AlertTriangle : state.active === 3 ? Check : state.active === null ? Info : CircleDot

  return <section aria-label="操作流程与当前状态" className="mt-5 rounded-[16px] border border-line bg-canvas/60 px-3 pb-4 pt-4 sm:px-4">
    <ol aria-label="操作步骤" className="grid grid-cols-4">
      {items.map((item, index) => {
        const done = index <= state.doneThrough
        const current = index === state.active && !done
        return <li key={item.number} aria-current={current ? 'step' : undefined}
          className="relative min-w-0 text-center">
          {index > 0 && <span aria-hidden="true" className={'absolute -left-1/2 top-[13px] h-px w-full ' +
            (index <= state.doneThrough ? 'bg-jade-600' : 'bg-line')}/>}
          <span aria-hidden="true" className={'relative mx-auto grid size-[27px] place-items-center rounded-full border text-[11px] font-semibold tabular-nums ' +
            (done ? 'action-journey-done border-jade-700 bg-jade-700 text-white' : current ? 'border-jade-700 bg-panel text-jade-800' : 'border-line bg-panel text-muted')}>
            {done ? <Check size={14} strokeWidth={2.3}/> : item.number}
          </span>
          <span className={'mt-2 block text-[10px] leading-[1.4] sm:text-[11px] ' +
            (done || current ? 'font-semibold text-ink' : 'text-muted')}>{item.label}</span>
        </li>
      })}
    </ol>
    <div className={'mt-4 flex items-start gap-2.5 rounded-xl px-3 py-3 ' +
      (state.caution ? 'action-caution bg-amber-50 text-amber-900' : 'bg-panel text-ink')}>
      <StatusIcon size={17} className="mt-0.5 shrink-0" aria-hidden="true"/>
      <div className="min-w-0">
        <p className="text-[12.5px] font-semibold">{busy ? '正在等待服务端响应' : state.heading}</p>
        <p className="mt-1 text-[11px] leading-[1.65] text-muted">
          {busy ? '请求仍在处理中，请勿重复操作或关闭窗口。' : state.explanation}
        </p>
      </div>
    </div>
  </section>
}
