import { PenguinArt } from '@/features/theme/PenguinArt'

/** One truthful visual language for loading and response generation.
 * No fabricated tool steps, percentage, ETA or transaction progress.
 */
export function AgentWorkingIndicator({ label = '正在整理回复', spacious = false }: {
  label?: string
  spacious?: boolean
}) {
  return <div role="status" aria-live="polite" className={'flex items-center gap-3 ' + (spacious ? 'py-1' : '')}>
    <div className="agent-working-character relative size-12 shrink-0">
      <span aria-hidden="true" className="absolute inset-1 rounded-full bg-jade-100/65" />
      <PenguinArt pose="thinking" className="relative size-full" />
    </div>
    <div className="min-w-0">
      <p className="text-[13px] font-medium tracking-[-0.012em] text-ink">{label}</p>
      <div aria-hidden="true" className="mt-2 flex items-center gap-1.5">
        <span className="agent-working-dot size-[5px] rounded-full bg-jade-600"/>
        <span className="agent-working-dot size-[5px] rounded-full bg-jade-500"/>
        <span className="agent-working-dot size-[5px] rounded-full bg-jade-400"/>
      </div>
    </div>
  </div>
}
