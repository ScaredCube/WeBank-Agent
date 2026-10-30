import type { ReactNode } from 'react'
import { useRef } from 'react'
import { ArrowLeftRight, ArrowRight, CalendarDays, CreditCard } from 'lucide-react'

const starterPrompts = [
  { label: '查一下我的账户余额', prompt: '查一下我的账户余额', icon: CreditCard },
  { label: '看看这个月的消费', prompt: '看看这个月的消费', icon: CalendarDays },
  { label: '准备给朋友转账', prompt: '准备给朋友转账', icon: ArrowLeftRight },
] as const

export function ChatHome({
  composer,
  onPick,
  disclaimer,
  feedback,
}: {
  composer: ReactNode
  onPick: (prompt: string) => void
  disclaimer?: ReactNode
  feedback?: ReactNode
}) {
  const homeRef = useRef<HTMLElement>(null)

  function pickPrompt(prompt: string) {
    onPick(prompt)
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
      className="mx-auto flex min-h-full w-full max-w-[820px] flex-col justify-center px-5 py-10 sm:px-8 xl:px-12"
    >
      <div className="w-full max-w-[704px]">
        <h2 id="chat-home-title" className="max-w-[610px] text-left text-[34px] font-bold leading-[1.13] tracking-[-0.035em] text-[#10231f] sm:text-[46px]">
          让金融事务<br />变得更简单
        </h2>
        <p className="mt-5 max-w-[520px] text-[14px] leading-7 text-muted sm:text-[16px]">
          查询账户、分析收支、了解资产。涉及转账等操作时，会先展示确认步骤。
        </p>

        {feedback}
        <div className="mt-7">{composer}</div>

        <div role="group" aria-label="常用问题" className="mt-6 grid w-full grid-cols-1 gap-2.5 sm:grid-cols-3 sm:gap-3">
          {starterPrompts.map(({ label, prompt, icon: Icon }) => (
            <button
              key={label}
              type="button"
              onClick={() => pickPrompt(prompt)}
              className="group flex min-h-[56px] w-full items-center gap-2.5 rounded-xl border border-line bg-white px-3 text-left text-[12px] font-semibold leading-5 text-ink transition-[background-color,border-color,transform] duration-150 hover:border-jade-300 hover:bg-[#f8fbf9] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 active:scale-[0.99] sm:min-h-[72px] sm:px-3.5 sm:text-[12.5px]"
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#edf5f1] text-jade-800 transition-colors group-hover:bg-jade-100">
                <Icon aria-hidden="true" className="size-[17px]" strokeWidth={1.8} />
              </span>
              <span className="min-w-0 flex-1">{label}</span>
              <ArrowRight aria-hidden="true" className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-jade-800" />
            </button>
          ))}
        </div>

        {disclaimer && (
          <p className="mt-5 max-w-[704px] text-center text-[11px] leading-5 text-muted sm:text-xs">
            {disclaimer}
          </p>
        )}
      </div>
    </section>
  )
}
