import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  UserRound,
} from 'lucide-react'

import { PenguinArt } from '@/features/theme/PenguinArt'
import { MascotStage } from '@/features/theme/MascotStage'
import { ThemeToggle } from '@/features/theme/ThemeToggle'
import { MASCOT_NAME, MASCOT_SLOGAN } from '@/features/theme/brand'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/use-auth'

export function LoginPage() {
  const { token, login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (token) navigate('/chat', { replace: true })
  }, [token, navigate])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (loading) return
    setLoading(true)
    setError(null)
    try {
      await login(username.trim(), password)
      navigate('/chat', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败，请稍后再试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="grid min-h-dvh bg-canvas text-ink lg:grid-cols-[minmax(0,1fr)_minmax(440px,1fr)]">
      <section aria-label="欢迎插画" className="relative hidden overflow-hidden border-r border-line bg-sidebar px-12 py-10 lg:flex lg:flex-col lg:justify-between">
        <div className="relative flex items-center gap-3">
          <PenguinArt pose="avatar" className="size-11" />
          <div className="min-w-0">
            <p className="text-[14px] font-semibold tracking-tight text-ink">{MASCOT_NAME}</p>
          </div>
        </div>

        <div className="relative mx-auto flex w-full max-w-[520px] flex-col items-start">
          <h1 className="text-[clamp(2.4rem,3.25vw,3.6rem)] font-semibold leading-[1.23] tracking-[-0.055em] text-ink">{MASCOT_SLOGAN}</h1>
          <div className="relative mx-auto -mb-6 mt-5">
            <MascotStage showcase />
          </div>
        </div>
        <p className="relative text-[12px] leading-5 text-muted">模拟银行业务环境 · 操作结果以服务端记录为准</p>
      </section>

      <section className="relative flex min-h-dvh flex-col px-6 py-8 sm:px-12 lg:px-16">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 lg:hidden">
            <PenguinArt pose="avatar" className="size-10" />
            <span className="text-sm font-semibold tracking-tight text-ink">{MASCOT_NAME}</span>
          </div>
          <ThemeToggle />
        </header>

        <div className="my-auto mx-auto w-full max-w-[380px] pb-12 pt-16 lg:py-12">
          <h2 className="text-[32px] font-semibold tracking-[-0.04em] text-ink">欢迎回来</h2>
          <p className="mt-2 text-sm leading-6 text-muted lg:hidden">{MASCOT_SLOGAN}</p>

          <form className="mt-10 space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="login-username" className="mb-2 block text-[13px] font-medium text-ink">账号</label>
              <div className="relative">
                <UserRound className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted/65" />
                <Input id="login-username" value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  autoComplete="username"
                  className="h-12 rounded-xl border-line bg-panel pl-11 text-[14px]"
                />
              </div>
            </div>

            <div>
              <label htmlFor="login-password" className="mb-2 block text-[13px] font-medium text-ink">密码</label>
              <div className="relative">
                <LockKeyhole className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted/65" />
                <Input id="login-password" type={showPassword ? 'text' : 'password'}
                  value={password} onChange={(event) => setPassword(event.target.value)}
                  autoComplete="current-password"
                  className="h-12 rounded-xl border-line bg-panel pl-11 pr-12 text-[14px]"
                />
                <button type="button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? '隐藏密码' : '显示密码'}
                  title={showPassword ? '隐藏密码' : '显示密码'}
                  className="absolute right-2 top-1/2 grid size-9 -translate-y-1/2 place-items-center rounded-lg text-muted transition-colors hover:bg-jade-50 hover:text-ink focus-visible:outline-2 focus-visible:outline-jade-700"
                >
                  {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            {error && <p role="alert" className="text-[13px] text-red-600">{error}</p>}

            <Button type="submit" disabled={loading || !username.trim() || !password}
              className="mt-3 h-12 w-full rounded-xl text-[14px] font-semibold">
              {loading && <LoaderCircle className="size-4 animate-spin" />}
              {loading ? '正在登录' : '登录'}
            </Button>
          </form>
          <p className="mt-8 text-center text-xs text-muted lg:hidden">模拟银行业务环境</p>
        </div>
      </section>
    </div>
  )
}
