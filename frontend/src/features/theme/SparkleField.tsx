import { useId } from 'react'

/** Each scene needs a distinct gradient ID; duplicated SVG IDs collide across cards. */
export function SparkleField({ tone = 'soft' }: { tone?: 'soft' | 'bright' }) {
  const gradientId = useId().replaceAll(':', '')
  return <svg viewBox="0 0 800 250" preserveAspectRatio="xMidYMid slice" aria-hidden="true" className="absolute inset-0 h-full w-full">
    <defs>
      <radialGradient id={gradientId}>
        <stop offset="0%" stopColor="var(--color-jade-200)" stopOpacity={tone === 'bright' ? '.45' : '.21'} />
        <stop offset="100%" stopColor="var(--color-jade-200)" stopOpacity="0" />
      </radialGradient>
    </defs>
    <ellipse cx="690" cy="30" rx="260" ry="155" fill={`url(#${gradientId})`} />
    <path d="M110 61v24M98 73h24M702 98v18M693 107h18M601 203v15M594 210h15" stroke="var(--color-jade-400)" strokeWidth="2.5" strokeLinecap="round" opacity=".45"/>
    <circle cx="167" cy="179" r="3" fill="var(--color-jade-400)" opacity=".35"/>
    <circle cx="656" cy="161" r="2.5" fill="var(--color-jade-400)" opacity=".36"/>
    <path d="M210 9q48 27 111 19" stroke="var(--color-jade-300)" opacity=".22" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="3 8"/>
  </svg>
}
