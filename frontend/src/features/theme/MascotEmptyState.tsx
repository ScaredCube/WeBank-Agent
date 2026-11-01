import { PenguinArt, type PenguinPose } from './PenguinArt'
import { SparkleField } from './SparkleField'

/**
 * Shared high-quality empty state: decorative visuals never replace semantic text.
 * Do not display celebratory imagery in pending, failed or uncertain financial operations.
 */
export function MascotEmptyState({ title, description, pose = 'sleep', compact = false }: {
  title: string
  description?: string
  pose?: PenguinPose
  compact?: boolean
}) {
  return <div className={'relative overflow-hidden rounded-[20px] border border-line bg-panel text-center ' +
    (compact ? 'px-4 py-5' : 'px-6 py-8')}>
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <SparkleField tone="soft" />
    </div>
    <div className="relative">
      <PenguinArt pose={pose} className={compact ? 'mx-auto size-20' : 'mx-auto size-28'} />
      <p className="mt-2 text-[13px] font-medium text-ink">{title}</p>
      {description && <p className="mx-auto mt-1 max-w-[260px] text-xs leading-5 text-muted">{description}</p>}
    </div>
  </div>
}
