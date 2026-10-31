import type { ReactNode } from 'react'
import { useTheme } from './theme-context'

export type StickerKind = 'receipt' | 'card' | 'chart' | 'shield' | 'star' | 'cloud'
const shapes: Record<StickerKind, ReactNode> = {
  receipt: <><path d="M28 13h42v69l-8-5-8 5-8-5-9 5-9-5V13Z" fill="#FFFDF8" stroke="#788E88" strokeWidth="2.5"/><path d="M38 28h21M38 39h24M38 50h14" stroke="#90A7A0" strokeWidth="3" strokeLinecap="round"/><circle cx="55" cy="65" r="9" fill="#F7CE84"/><path d="M55 60v10m-4-8c7-4 11 3 4 4-7 1-3 8 4 4" stroke="#AF7935" strokeWidth="1.7"/></>,
  card: <><rect x="12" y="23" width="74" height="52" rx="12" fill="#B8DDD3" stroke="#609D8C" strokeWidth="2.5"/><path d="M12 38h74" stroke="#3D8976" strokeWidth="7"/><rect x="23" y="53" width="16" height="11" rx="3.5" fill="#FCF1C7"/><circle cx="66" cy="59" r="7" fill="#F5E9DD" opacity=".85"/><circle cx="74" cy="59" r="7" fill="#FCF1C7" opacity=".9"/></>,
  chart: <><rect x="15" y="14" width="70" height="70" rx="16" fill="#E4EBF5" stroke="#8EA9D1" strokeWidth="2.5"/><path d="M28 67 44 51 55 58 71 32" stroke="#5487C9" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round"/><path d="m62 31 10-1-1 10" stroke="#5487C9" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/><circle cx="28" cy="67" r="5" fill="#FFD48E"/></>,
  shield: <><path d="M50 10 80 23v25c0 21-15 33-30 40C35 81 20 69 20 48V23l30-13Z" fill="#CDE5DA" stroke="#70AA94" strokeWidth="3"/><path d="m36 49 10 10 18-22" stroke="#3A856D" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"/></>,
  star: <><path d="m50 8 11 29 31 3-24 20 8 31-26-17-26 17 8-31L8 40l31-3L50 8Z" fill="#FFD48E" stroke="#E8AE53" strokeWidth="3"/><path d="M50 20v17" stroke="#FFF5C7" strokeWidth="4" strokeLinecap="round"/></>,
  cloud: <><path d="M26 71h48c13 0 16-16 7-24-4-4-9-5-14-5C64 20 33 19 28 40 10 37 6 68 26 71Z" fill="#D9E8F8" stroke="#93B1D5" strokeWidth="3"/><path d="m39 50 7 6 14-14" stroke="#6695CD" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"/></>,
}
/** Theme-neutral mini illustrations rendered as real SVG, no bitmap downloads. */
export function FinanceSticker({ kind, className = 'size-10' }: { kind: StickerKind; className?: string }) {
  const { resolved } = useTheme()
  return <svg viewBox="0 0 100 100" aria-hidden="true" className={className} style={{ filter: resolved === 'dark' ? 'brightness(.88) saturate(.82)' : undefined }}>
    {shapes[kind]}
  </svg>
}
