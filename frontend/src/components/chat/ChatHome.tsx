import { useRef, type ReactNode } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { MascotStage } from '@/features/theme/MascotStage'
import { FinanceSticker, type StickerKind } from '@/features/theme/FinanceSticker'

export interface ChatStarterPrompt {
  label: string
  prompt: string
  art: StickerKind
}

interface ChatHomeProps {
  composer: ReactNode
  suggestions?: readonly ChatStarterPrompt[]
  onPick?: (prompt: string) => void
  feedback?: ReactNode
  disclaimer?: ReactNode
}

/** Presentation only. Authentication, data fetching and conversations belong to the page. */
export function ChatHome({
  composer, suggestions = [], onPick, feedback, disclaimer,
}: ChatHomeProps) {
  const homeRef = useRef<HTMLElement>(null)
  const reduceMotion = useReducedMotion()

  function pickPrompt(prompt: string) {
    if (!onPick) return
    onPick(prompt)
    const focusInput = () => {
      const input = homeRef.current?.querySelector('textarea')
      if (input) {
        input.focus()
        input.setSelectionRange(input.value.length, input.value.length)
      }
    }
    if (typeof window.requestAnimationFrame === 'function') window.requestAnimationFrame(focusInput)
    else window.setTimeout(focusInput, 0)
  }

  return (
    <section
      ref={homeRef}
      aria-labelledby="chat-home-title"
      className="bank-home mx-auto flex min-h-full w-full max-w-[1100px] flex-col px-6 pb-10 pt-8 sm:px-10 sm:pt-10 lg:px-14 xl:px-16 xl:pt-12"
    >
      <div className="grid flex-1 items-center py-8 lg:py-10">
        <div className="relative w-full">
          <div className="flex items-baseline gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-4">
                <h2 id="chat-home-title"
                  className="min-w-0 max-w-[700px] text-balance text-[clamp(2.15rem,4vw,3.9rem)] font-semibold leading-[1.18] tracking-[-0.045em] text-ink">
                  今天，<span className="block sm:inline lg:block xl:inline">想完成什么？</span>
                </h2>
                <MascotStage />
              </div>

              <div className="mt-8 w-full lg:mt-10">
                {composer}
                {feedback}
              </div>

              {onPick && suggestions.length > 0 && (
                <nav className="mt-10" aria-label="常用事务，选择后填入输入框">
                  <div className="mb-4 flex items-center justify-between">
                    <h3 className="text-[16px] font-semibold tracking-tight text-ink">常用事务</h3>
                  </div>
                  <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                    {suggestions.map(({ label, prompt, art }) => (
                      <motion.button
                        key={prompt}
                        type="button"
                        onClick={() => pickPrompt(prompt)}
                        whileHover={reduceMotion ? undefined : { y: -2 }}
                        whileTap={reduceMotion ? undefined : { scale: 0.985 }}
                        transition={{ type: 'spring', stiffness: 430, damping: 32 }}
                        className={'group relative flex min-h-[96px] w-full items-center gap-4 rounded-[18px] border border-line bg-panel px-5 py-4 text-left shadow-[0_8px_25px_-24px_rgba(0,40,31,.3)] transition hover:border-jade-300 hover:bg-jade-50/30 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-jade-700'}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-2.5">
                          <span className="grid size-11 shrink-0 place-items-center rounded-2xl bg-jade-50"><FinanceSticker kind={art} className="size-9" /></span>
                          <span className="text-[14px] font-semibold tracking-[-0.02em] text-ink">{label}</span>
                        </span>
                        <ArrowUpRight aria-hidden="true" size={17} className="shrink-0 text-muted/65 transition-colors group-hover:text-jade-700" />
                      </motion.button>
                    ))}
                  </div>
                </nav>
              )}
            </div>
          </div>
        </div>
      </div>

      {disclaimer && <p className="mt-7 text-[10.5px] leading-5 text-muted/75">
        {disclaimer}
      </p>}
    </section>
  )
}
