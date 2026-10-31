import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Moon, Sun, Sparkles } from 'lucide-react'
import { PenguinArt, type PenguinPose } from '@/features/theme/PenguinArt'
import { MascotEmptyState } from '@/features/theme/MascotEmptyState'
import { SparkleField } from '@/features/theme/SparkleField'
import { FinanceSticker, type StickerKind } from '@/features/theme/FinanceSticker'
import { useTheme } from '@/features/theme/theme-context'
import { MASCOT_NAME } from '@/features/theme/brand'

const poses: { id: PenguinPose; label: string; description: string }[] = [
  { id: 'hero', label: '欢迎', description: '首次进入 / 品牌记忆' },
  { id: 'avatar', label: '头像', description: '对话及导航身份' },
  { id: 'thinking', label: '思考', description: 'Agent 处理中' },
  { id: 'celebrate', label: '庆祝', description: '服务端成功后' },
  { id: 'sleep', label: '睡觉', description: '空态与等待' },
  { id: 'peek', label: '探头', description: '引导和轻提示' },
]

export default function IPStudio() {
  const { resolved, toggle } = useTheme()
  const [active, setActive] = useState<PenguinPose>('thinking')
  return <div className="min-h-dvh bg-canvas px-5 py-8 text-ink sm:px-10 lg:px-16">
    <header className="mx-auto flex max-w-[1240px] items-center justify-between gap-4 border-b border-line pb-5">
      <Link to="/product-preview?state=empty" className="inline-flex items-center gap-2 text-sm font-medium text-muted hover:text-ink"><ArrowLeft size={16}/> 返回产品</Link>
      <button type="button" onClick={() => toggle()} className="inline-flex min-h-11 items-center gap-2 rounded-full border border-line bg-panel px-4 text-sm focus-visible:outline-2 focus-visible:outline-jade-700">
        {resolved === 'dark' ? <Sun size={16}/> : <Moon size={16}/>} {resolved === 'dark' ? '夜间主题' : '日间主题'}
      </button>
    </header>

    <main className="mx-auto max-w-[1240px]">
      <div className="mt-14 max-w-[800px]">
        <p className="text-xs font-medium tracking-[0.12em] text-jade-700">WEBANK AGENT · IP LAB</p>
        <h1 className="mt-4 text-[clamp(2.2rem,4.1vw,4rem)] font-semibold tracking-[-0.06em]">{MASCOT_NAME} · 双主题素材</h1>
        <p className="mt-5 text-sm leading-7 text-muted">这是只在本地开发环境开放的素材试验台。每个角色状态会随明暗主题自动映射。图形衍生元素使用 SVG/CSS，图片加载失败时回退到简化角色。</p>
      </div>
      <section className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="角色姿态">
        {poses.map(({ id, label, description }) => <button type="button" key={id} onClick={() => setActive(id)}
          aria-pressed={active === id}
          style={{ backgroundColor: active === id ? "var(--ip-card-active)" : "var(--color-panel)", color: "var(--color-ink)" }}
          className={'group relative flex min-h-[240px] flex-col items-center justify-between rounded-[24px] border px-5 pb-5 pt-4 text-center transition-transform duration-200 hover:-translate-y-0.5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-jade-700 ' + (active === id ? 'border-jade-400 bg-jade-50/40' : 'border-line bg-panel')}>
          <div className="grid h-[156px] place-items-center"><PenguinArt pose={id} className="size-[150px]" /></div>
          <div className="w-full border-t border-line pt-3">
            <p className="text-[14px] font-semibold">{label}</p>
            <p className="mt-1 text-xs text-muted">{description}</p>
          </div>
        </button>)}
      </section>

      <section className="mt-14 grid gap-4 lg:grid-cols-[1.5fr_1fr]" aria-label="状态与动态图形">
        <div className="relative min-h-[340px] overflow-hidden rounded-[26px] border border-line bg-panel p-8">
          <div aria-hidden="true" className="pointer-events-none absolute inset-0"><SparkleField tone="bright"/></div>
          <div className="relative flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium text-jade-700">场景合成 / CSS + SVG</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight">{MASCOT_NAME}与光点</h2>
              <p className="mt-2 max-w-[360px] text-sm leading-6 text-muted">背景星点与柔和氛围由浏览器绘制，支持主题色变化，无需加载整张背景图。</p>
            </div>
            <Sparkles className="shrink-0 text-jade-500" size={22} />
          </div>
          <PenguinArt pose={active} className="absolute bottom-0 right-4 size-[230px] sm:right-10" />
        </div>
        <div className="grid gap-4">
          <MascotEmptyState title="这里还没有收藏" description="把喜欢的分析卡片留在这里。" pose="peek" />
          <div className="relative flex min-h-[100px] items-center gap-4 overflow-hidden rounded-2xl border border-line bg-panel px-4">
            <PenguinArt pose="thinking" className="size-16"/>
            <div><p className="text-sm font-semibold">正在整理信息</p><p className="mt-1 text-xs text-muted">处理过程有明确的文字状态</p></div>
          </div>
        </div>
      </section>
      <section className="mt-12 border-t border-line pt-9">
        <h2 className="text-xl font-semibold tracking-tight">矢量图形素材 · SVG</h2>
        <p className="mt-2 text-sm leading-6 text-muted">账单、卡片、图表与装饰图标由浏览器绘制，适配分辨率与主题，不必为每一种尺寸制作图片。</p>
        <div className="mt-6 grid grid-cols-3 gap-3 sm:grid-cols-6">
          {(['receipt','card','chart','shield','star','cloud'] as StickerKind[]).map(kind =>
            <div key={kind} className="flex flex-col items-center gap-3 rounded-2xl border border-line bg-panel px-2 py-6">
              <FinanceSticker kind={kind} className="size-16" />
              <span className="text-xs text-muted">{kind}</span>
            </div>)}
        </div>
      </section>
      <p className="pb-16 pt-8 text-xs text-muted">本页面只供样式与素材验收，不包含真实银行数据或业务请求。</p>
    </main>
  </div>
}
