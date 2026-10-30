import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  UserRound,
} from 'lucide-react'

import { BrandMark } from '@/components/BrandMark'
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
    <div className="grid min-h-dvh lg:grid-cols-[1.08fr_1fr]">
      <section className="relative hidden overflow-hidden bg-jade-950 p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute -right-36 -top-40 size-[520px] rounded-full bg-jade-600/25 blur-[130px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-40 -left-24 size-[460px] rounded-full bg-jade-500/12 blur-[110px]"
        />

        <div className="relative flex items-center gap-3">
          <BrandMark className="size-10 rounded-xl bg-white/10 text-white ring-1 ring-white/15" />
          <div>
            <div className="text-[15px] font-medium tracking-wide">微众银行AI智能体</div>
          </div>
        </div>

        <div className="relative">
          <h1 className="text-[46px] font-medium leading-[1.16] tracking-[-0.025em]">
            想办的事，
            <br />
            从对话开始。
          </h1>
          <p className="mt-6 max-w-[360px] text-[14.5px] leading-relaxed text-white/50">
            查询账户信息，了解收支，按步骤核对需要确认的操作。
          </p>
        </div>

        <div className="relative text-[11.5px] text-white/55">模拟业务环境</div>
      </section>

      <section className="flex min-h-dvh items-center justify-center px-6 py-12">
        <div className="w-full max-w-[360px]">
          <div className="mb-10 flex items-center gap-3 lg:hidden">
            <BrandMark className="size-10 rounded-xl" />
            <div>
              <div className="text-[15px] font-medium tracking-wide text-ink">微众银行AI智能体</div>
            </div>
          </div>

          <h2 className="text-[28px] font-medium tracking-tight text-ink">欢迎回来</h2>
          <p className="mt-2 text-[13.5px] text-muted">登录后继续与你的 AI 管家对话</p>

          <form className="mt-8 space-y-3.5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="login-username" className="mb-2 block text-sm font-medium text-ink">账号</label>
              <div className="relative">
              <UserRound className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted/55" />
              <Input
                id="login-username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                autoComplete="username"
                className="h-12 rounded-xl pl-10 text-[14px]"
              />
              </div>
            </div>

            <div>
              <label htmlFor="login-password" className="mb-2 block text-sm font-medium text-ink">密码</label>
              <div className="relative">
              <LockKeyhole className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted/55" />
              <Input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="h-12 rounded-xl pl-10 pr-11 text-[14px]"
              />
              <button
                type="button"
                onClick={() => setShowPassword((current) => !current)}
                className="absolute right-2 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-lg text-muted/55 transition hover:bg-ink/5 hover:text-ink"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                <span className="sr-only">{showPassword ? '隐藏密码' : '显示密码'}</span>
              </button>
              </div>
            </div>

            {error && <p role="alert" className="text-[12.5px] text-red-600">{error}</p>}

            <Button
              type="submit"
              disabled={loading || !username.trim() || !password}
              className="h-12 w-full rounded-xl text-[14.5px]"
            >
              {loading && <LoaderCircle className="size-4 animate-spin" />}
              {loading ? '正在登录' : '登录'}
            </Button>
          </form>

        </div>
      </section>
    </div>
  )
}
