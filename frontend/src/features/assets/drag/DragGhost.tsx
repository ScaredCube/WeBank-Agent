import { createPortal } from 'react-dom'
import type { DragGhostState } from './useAssetDrag'

export function DragGhost({ state, reduced }: { state: DragGhostState | null; reduced: boolean }) {
  if (!state || typeof document === 'undefined') return null
  return createPortal(
    <div
      aria-hidden="true"
      className="pointer-events-none fixed z-[100] opacity-95"
      style={{
        width: state.width, height: state.height,
        left: state.x - state.offsetX, top: state.y - state.offsetY,
        transform: reduced ? undefined : 'scale(1.035) rotate(-1deg)',
        filter: 'drop-shadow(0 22px 30px rgba(0,0,0,.35))',
        transition: 'none',
      }}
    >
      <div className="asset-ghost-card h-full w-full overflow-hidden rounded-[18px] border border-white/30 bg-panel p-4 shadow-2xl">
        <p className="text-[11px] uppercase tracking-[0.18em] text-muted">{state.item.kind === 'account' ? '银行卡' : state.item.kind === 'contact' ? '联系人' : '持仓'}</p>
        <p className="mt-2 truncate text-sm font-semibold text-ink">{state.item.label}</p>
        {state.item.detail ? <p className="mt-1 truncate text-xs text-muted">{state.item.detail}</p> : null}
      </div>
    </div>,
    document.body,
  )
}
