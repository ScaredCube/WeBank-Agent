import { useRef, type ReactNode } from 'react'
import { ArrowUpRight } from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'

import { HomeAccountSummary } from '@/components/chat/HomeAccountSummary'
import { MascotStage } from '@/features/theme/MascotStage'
import { FinanceSticker, type StickerKind } from '@/features/theme/FinanceSticker'
import type { HomeOverview } from '@/features/home/useHomeAccountOverview'

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
  overview?: HomeOverview
  mode?: 'full' | 'sidecar'
  hidden?: boolean
  onTogglePrivacy?: () => void
  onOpenAssets?: () => void
}

const emptyOverview: HomeOverview = { status: 'ready', data: null }

/** Presentation only. Authentication, data fetching and conversations belong to the page. */
export function ChatHome({
  composer, suggestions = [], onPick, feedback, disclaimer,
  overview = emptyOverview, mode = 'full', hidden = false,
  onTogglePrivacy, onOpenAssets,
}: ChatHomeProps) {
  const homeRef = useRef<HTMLElement>(null)
  const reduceMotion = useReducedMotion()
  const compact = mode === 'sidecar'

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
      data-home-mode={mode}
      className={'bank-home mx-auto flex min-h-full w-full max-w-[1240px] flex-col px-6 pb-10 pt-8 sm:px-10 sm:pt-10 ' +
        (compact ? 'lg:px-10 lg:pt-14' : 'lg:px-16 xl:px-20 xl:pt-12')}
    >
      <div className="flex items-center justify-between gap-4 border-b border-line pb-5">
        <div className="flex items-center gap-2.5">
          <span aria-hidden="true" className="block size-1.5 rounded-full bg-jade-700" />
          <span className="text-[11px] font-semibold tracking-[0.12em] text-muted">新委托</span>
        </div>
      </div>

      <div className={'grid flex-1 items-center ' + (compact ? 'py-8' : 'py-8 lg:py-10')}>
        <div className="relative w-full">
          <div className="relative flex items-baseline gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-4">
                <h2 id="chat-home-title"
                  className={'min-w-0 max-w-[700px] text-balance font-semibold leading-[1.18] tracking-[-0.045em] text-ink ' +
                    (compact ? 'text-[clamp(1.9rem,3vw,2.7rem)]' : 'text-[clamp(2.15rem,4vw,3.9rem)]')}>
                  今天，<span className="block sm:inline">想完成什么？</span>
                </h2>
                {!compact && <MascotStage />}
              </div>

              <div className={'w-full ' + (compact ? 'mt-9' : 'mt-8 lg:mt-10')}>
                {composer}
                {feedback}
              </div>

              {!compact && onPick && suggestions.length > 0 && (
                <nav className="mt-10" aria-label="常用事务，选择后填入输入框">
                  <div className="flex items-center justify-between border-b border-line pb-3">
                    <h3 className="text-[12px] font-semibold text-ink">常用事务</h3>
                    <span className="text-[11px] text-muted">选择后可修改</span>
                  </div>
                  <div className="grid md:grid-cols-3">
                    {suggestions.map(({ label, prompt, art }) => (
                      <motion.button
                        key={prompt}
                        type="button"
                        onClick={() => pickPrompt(prompt)}
                        whileHover={reduceMotion ? undefined : { y: -2 }}
                        whileTap={reduceMotion ? undefined : { scale: 0.985 }}
                        transition={{ type: 'spring', stiffness: 430, damping: 32 }}
                        className={'group relative flex min-h-[76px] w-full items-center gap-3 border-b border-line py-3 text-left transition-colors hover:bg-jade-50/45 focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-jade-700 ' +
                          'px-2 md:border-r md:px-4 md:first:pl-0 md:last:border-r-0'}
                      >
                        <span className="flex min-w-0 flex-1 items-center gap-2.5">
                          <FinanceSticker kind={art} className="size-9 shrink-0" />
                          <span className="text-[13px] font-medium tracking-[-0.02em] text-ink">{label}</span>
                        </span>
                        <ArrowUpRight aria-hidden="true" size={15} className="shrink-0 text-muted/50 transition-colors group-hover:text-jade-700" />
                      </motion.button>
                    ))}
                  </div>
                </nav>
              )}
            </div>
          </div>
        </div>
      </div>

      {!compact && (
        <HomeAccountSummary
          overview={overview}
          hidden={hidden}
          onTogglePrivacy={onTogglePrivacy}
          onOpenAssets={onOpenAssets}
        />
      )}

      {disclaimer && <p className={'text-[10.5px] leading-5 text-muted/75 ' + (compact ? 'mt-10' : 'mt-7')}>
        {disclaimer}
      </p>}
    </section>
  )
}
