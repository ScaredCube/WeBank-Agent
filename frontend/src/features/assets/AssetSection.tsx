import type { ReactNode } from 'react'

export function AssetSection({ id, title, count, children }: {
  id?: string
  title: string
  count?: number
  children: ReactNode
}) {
  return (
    <section id={id} className="scroll-mt-[68px]">
      <h3 className="mb-3 flex items-baseline gap-2 text-sm font-semibold text-ink">
        <span>{title}</span>
        {count !== undefined && <span className="text-xs font-normal tabular-nums text-muted">{count}</span>}
      </h3>
      {children}
    </section>
  )
}
