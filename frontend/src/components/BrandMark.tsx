import { cn } from '@/lib/utils'

export function BrandMark({ className }: { className?: string }) {
  return (
    <div
      aria-hidden
      className={cn(
        'grid shrink-0 place-items-center rounded-[10px] bg-jade-700 text-jade-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.14)]',
        className,
      )}
    >
      <svg viewBox="0 0 24 24" fill="none" className="size-[58%]">
        <path
          d="M3.6 9.4 12 4.6l8.4 4.8M5.6 10.4v6.4M9.3 10.4v6.4M14.7 10.4v6.4M18.4 10.4v6.4M4 19.4h16"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  )
}
