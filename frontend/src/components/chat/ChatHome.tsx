import type { ReactNode } from 'react'
import { useRef } from 'react'
import { ArrowRight, type LucideIcon } from 'lucide-react'

export interface ChatStarterPrompt {
  label: string
  prompt: string
  icon: LucideIcon
}

export function ChatHome({
  composer,
  suggestions = [],
  onPick,
  disclaimer,
  feedback,
}: {
  composer: ReactNode
  suggestions?: readonly ChatStarterPrompt[]
  onPick?: (prompt: string) => void
  disclaimer?: ReactNode
  feedback?: ReactNode
}) {
  const homeRef = useRef<HTMLElement>(null)

  function pickPrompt(prompt: string) {
    onPick?.(prompt)
    const focusComposer = () => {
      const textarea = homeRef.current?.querySelector('textarea')
      if (!textarea) return
      textarea.focus()
      textarea.setSelectionRange(textarea.value.length, textarea.value.length)
    }
    if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(focusComposer)
    else window.setTimeout(focusComposer, 0)
  }

  return (
    <section
      ref={homeRef}
      aria-labelledby="chat-home-title"
      className="mx-auto flex min-h-full w-full max-w-[820px] flex-col justify-center px-5 py-8 sm:px-8 lg:-translate-y-8 xl:px-12"
    >
      <div className="w-full max-w-[704px]">
        <h2 id="chat-home-title" className="max-w-[704px] text-balance text-left text-[34px] font-bold leading-[1.1] tracking-[-0.035em] text-[#10231f] sm:text-[46px]">
          让金融事务变得更简单
        </h2>
        <p className="mt-3 max-w-[704px] text-pretty text-[14px] leading-7 text-muted sm:text-[16px]">
          账户、收支、资产可直接查询；转账需先确认。
        </p>

        {feedback}
        <div className="mt-5">{composer}</div>

        {suggestions.length > 0 && onPick && <div role="group" aria-label="示例问题" className="mt-5 flex w-full flex-wrap gap-2.5">
          {suggestions.map(({ label, prompt, icon: Icon }) => (
            <button
              key={`${label}:${prompt}`}
              type="button"
              onClick={() => pickPrompt(prompt)}
              className="group flex min-h-12 min-w-[180px] flex-1 items-center gap-2.5 rounded-xl border border-line bg-white px-3 text-left text-[12.5px] font-semibold leading-5 text-ink transition-[background-color,border-color,transform] duration-150 hover:border-jade-300 hover:bg-[#f8fbf9] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 active:scale-[0.99]"
            >
              <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[#edf5f1] text-jade-800 transition-colors group-hover:bg-jade-100">
                <Icon aria-hidden="true" className="size-4" strokeWidth={1.8} />
              </span>
              <span className="min-w-0 flex-1">{label}</span>
              <ArrowRight aria-hidden="true" className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-jade-800" />
            </button>
          ))}
        </div>}

        {disclaimer && (
          <p className="mt-2 max-w-[704px] text-left text-xs leading-5 text-muted">
            {disclaimer}
          </p>
        )}
      </div>
    </section>
  )
}
