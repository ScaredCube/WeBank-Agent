import { useState, type CSSProperties } from 'react'
import { useTheme } from '@/features/theme/theme-context'
import { MASCOT_NAME } from '@/features/theme/brand'
import { cn } from '@/lib/utils'

export type PenguinPose = 'hero' | 'avatar' | 'thinking' | 'celebrate' | 'sleep' | 'peek'

const imagePaths = {
  light: {
    hero: '/ip/penguin-charcoal-hero-480.webp',
    avatar: '/ip/penguin-charcoal-avatar-192.webp',
    thinking: '/ip/penguin-charcoal-thinking-384.webp',
    celebrate: '/ip/penguin-charcoal-celebrate-384.webp',
    sleep: '/ip/penguin-charcoal-sleep-384.webp',
    peek: '/ip/penguin-charcoal-peek-384.webp',
  },
  dark: {
    hero: '/ip/penguin-silver-hero-480.webp',
    avatar: '/ip/penguin-silver-avatar-192.webp',
    thinking: '/ip/penguin-silver-thinking-384.webp',
    celebrate: '/ip/penguin-silver-celebrate-384.webp',
    sleep: '/ip/penguin-silver-sleep-384.webp',
    peek: '/ip/penguin-silver-peek-384.webp',
  },
} as const

/** Illustrated, pose-specific fallback while the original fluffy artwork is not installed.
 * Same silhouette and scarf identity; each state has a distinct readable expression.
 */
function VectorFallback({ silver, pose }: { silver: boolean; pose: PenguinPose }) {
  const fur = silver ? '#B7C0D4' : '#373846'
  const scarf = silver ? '#559DEB' : '#E84E52'
  const asleep = pose === 'sleep'
  const happy = pose === 'celebrate'
  const thinking = pose === 'thinking'
  const peeking = pose === 'peek'
  const avatar = pose === 'avatar'
  const viewBox = avatar ? '19 19 142 133' : '0 0 180 180'
  return <svg viewBox={viewBox} fill="none" className="h-full w-full" aria-hidden="true">
    {!avatar && <ellipse cx="90" cy="166" rx="55" ry="6" fill="currentColor" opacity=".07" />}
    {happy && <>
      <path d="m18 40 7-7m-2 13 7 3m132-13 6-5m-4 16-7 3" stroke={scarf} strokeWidth="4" strokeLinecap="round"/>
      <circle cx="25" cy="64" r="3.5" fill="#FFC56B"/>
      <circle cx="157" cy="67" r="3.5" fill="#FFC56B"/>
    </>}
    {thinking && <>
      <circle cx="157" cy="42" r="15" fill={silver ? '#D7E8FE' : '#FFE0BC'} />
      <path d="M151 38q4-9 11-3 4 5-2 9-4 2-4 5" stroke="#795B44" strokeWidth="2.7" strokeLinecap="round"/>
      <circle cx="157" cy="53" r="1.5" fill="#795B44"/>
    </>}
    {asleep && <>
      <path d="M138 42h14l-14 13h14M154 21h11l-11 10h11" stroke={silver ? '#7EADE4' : '#F19B92'} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"/>
    </>}
    <g transform={asleep ? 'rotate(13 90 104)' : undefined}>
      <ellipse cx="90" cy="92" rx="65" ry="70" fill={fur}/>
      <path d="M79 25Q84 10 111 24" stroke={fur} strokeWidth="12" strokeLinecap="round"/>
      <ellipse cx="90" cy="118" rx="46" ry="43" fill="#FFFBF6"/>
      <ellipse cx="57" cy="77" rx="30" ry="35" fill="#FFFBF6"/>
      <ellipse cx="123" cy="77" rx="30" ry="35" fill="#FFFBF6"/>

      {asleep || happy ? <>
        <path d="M57 78q11 12 22 0M101 78q11 12 22 0" stroke="#253041" strokeWidth="4.3" strokeLinecap="round"/>
      </> : <>
        <ellipse cx={thinking ? 71 : 68} cy={thinking ? 75 : 78} rx="10.5" ry="14" fill="#182437"/>
        <ellipse cx={thinking ? 115 : 112} cy={thinking ? 75 : 78} rx="10.5" ry="14" fill="#182437"/>
        <circle cx={thinking ? 75 : 71} cy={thinking ? 70 : 73} r="3.5" fill="white"/>
        <circle cx={thinking ? 119 : 115} cy={thinking ? 70 : 73} r="3.5" fill="white"/>
      </>}
      <ellipse cx="41" cy="97" rx="10" ry="6" fill="#F5B9BC" opacity=".78"/>
      <ellipse cx="139" cy="97" rx="10" ry="6" fill="#F5B9BC" opacity=".78"/>
      {happy ? <>
        <path d="M77 91q13-5 26 0-4 22-13 22-10 0-13-22Z" fill="#F4A94D"/>
        <path d="M82 101q8-4 16 0" stroke="#E88782" strokeWidth="4" strokeLinecap="round"/>
      </> : <>
        <path d={thinking ? 'M78 91q14-7 25 1-14 7-25-1Z' : 'M76 92Q89 82 103 92Q90 107 76 92Z'} fill="#F9B755"/>
      </>}
      <path d="M46 112Q87 128 137 111" stroke={scarf} strokeWidth="17" strokeLinecap="round"/>
      <path d="M116 111v36q0 9 10 9h6q8 0 8-9v-33" fill={scarf}/>
      {happy ? <>
        <path d="M40 116Q20 107 19 80" stroke={fur} strokeWidth="17" strokeLinecap="round"/>
        <path d="M141 115Q163 100 163 80" stroke={fur} strokeWidth="17" strokeLinecap="round"/>
      </> : thinking ? <>
        <path d="M43 118q-18 1-20 12" stroke={fur} strokeWidth="19" strokeLinecap="round"/>
        <path d="M139 118Q125 97 114 95" stroke={fur} strokeWidth="18" strokeLinecap="round"/>
      </> : peeking ? <>
        <path d="M42 118Q23 104 15 124" stroke={fur} strokeWidth="18" strokeLinecap="round"/>
        <path d="M139 116q24-12 29 10" stroke={fur} strokeWidth="18" strokeLinecap="round"/>
      </> : <>
        <path d="M42 117Q23 110 17 128" stroke={fur} strokeWidth="18" strokeLinecap="round"/>
        <path d="M140 117Q158 106 164 128" stroke={fur} strokeWidth="18" strokeLinecap="round"/>
      </>}
      <ellipse cx="62" cy="164" rx="17" ry="9" fill="#FFBD53"/>
      <ellipse cx="118" cy="164" rx="17" ry="9" fill="#FFBD53"/>
    </g>
    {peeking && <path d="M16 152q74 16 148 0v22H16Z" fill={silver ? '#DCE9FA' : '#E1EDE7'} stroke={silver ? '#B7CFE9' : '#9EBEB1'} strokeWidth="2" />}
  </svg>
}

export function PenguinArt({ pose = 'hero', className, decorative = true, style, eager = false }: {
  pose?: PenguinPose
  className?: string
  decorative?: boolean
  style?: CSSProperties
  eager?: boolean
}) {
  const { resolved } = useTheme()
  const src = imagePaths[resolved][pose]
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  const size = pose === 'avatar' ? 192 : pose === 'hero' ? 480 : 384
  return <span
    className={cn('inline-flex shrink-0 items-center justify-center select-none', className)}
    style={style}
    role={decorative ? undefined : 'img'}
    aria-label={decorative ? undefined : resolved === 'light' ? `${MASCOT_NAME}，戴红围巾的黑企鹅` : `${MASCOT_NAME}，戴蓝围巾的浅灰企鹅`}
    aria-hidden={decorative ? true : undefined}
  >
    {failedSrc === src ? <VectorFallback silver={resolved === 'dark'} pose={pose}/> : <img
      src={src}
      onError={() => setFailedSrc(src)}
      alt=""
      width={size}
      height={size}
      loading={eager ? 'eager' : 'lazy'}
      decoding="async"
      draggable={false}
      className="h-full w-full object-contain"
    />}
  </span>
}
