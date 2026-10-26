import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, LoaderCircle, Menu, ShieldCheck } from 'lucide-react'

import { ActionConfirmDialog } from '@/components/ActionConfirmDialog'
import { BrandMark } from '@/components/BrandMark'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { ConversationSidebar } from '@/components/chat/ConversationSidebar'
import { MessageList } from '@/components/chat/MessageList'
import {
  ApiError,
  api,
  type Conversation,
  type Health,
  type Message,
} from '@/lib/api'
import { useAuth } from '@/lib/use-auth'
import { streamChat } from '@/lib/sse'
import { cn } from '@/lib/utils'

const SUGGESTIONS = ['查一下我的账户余额', '帮我分析这个月的消费', '我要给朋友转账']

function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="mx-auto flex h-full min-h-[420px] max-w-[620px] flex-col items-center justify-center px-6 pb-10 text-center">
      <BrandMark className="size-12 rounded-2xl shadow-[0_14px_34px_-16px_rgba(11,95,69,0.55)]" />
      <h2 className="mt-5 text-[24px] font-medium tracking-tight text-ink">
        今天想办点什么？
      </h2>
      <p className="mt-2 text-[13px] text-muted/70">直接说出你的需求，剩下的交给我。</p>
      <div className="mt-7 flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            onClick={() => onPick(text)}
            className="rounded-full border border-line bg-white/70 px-3.5 py-1.5 text-[12.5px] text-ink/65 transition hover:border-jade-200 hover:bg-jade-50 hover:text-jade-800"
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ChatPage() {
  const { token, user, logout } = useAuth()
  const navigate = useNavigate()

  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)

  const scrollRef = useRef<HTMLDivElement>(null)
  const noticeTimer = useRef<number | null>(null)

  useEffect(() => {
    if (!token) return
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null))
  }, [token])

  useEffect(() => {
    if (!token) return
    let cancelled = false

    void (async () => {
      try {
        const list = await api.conversations(token)
        if (cancelled) return
        setConversations(list)
        if (list.length > 0) {
          const first = list[0]
          setActiveId(first.id)
          const history = await api.messages(token, first.id)
          if (!cancelled) setMessages(history)
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : '会话加载失败')
      } finally {
        if (!cancelled) setLoadingMessages(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [token])

  useEffect(() => {
    const container = scrollRef.current
    if (container) container.scrollTop = container.scrollHeight
  }, [messages, streamingText, sending, loadingMessages])

  useEffect(
    () => () => {
      if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    },
    [],
  )

  const openConversation = useCallback(
    async (id: number) => {
      if (sending || !token) return
      setSidebarOpen(false)
      setActiveId(id)
      setError(null)
      setLoadingMessages(true)
      try {
        const history = await api.messages(token, id)
        setMessages(history)
        setStreamingText('')
      } catch (err) {
        setError(err instanceof Error ? err.message : '会话加载失败')
      } finally {
        setLoadingMessages(false)
      }
    },
    [sending, token],
  )

  const createConversation = useCallback(async () => {
    if (sending || !token) return
    try {
      const conversation = await api.createConversation(token)
      setConversations((prev) => [conversation, ...prev])
      setActiveId(conversation.id)
      setMessages([])
      setDraft('')
      setError(null)
      setSidebarOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : '新建会话失败')
    }
  }, [sending, token])

  const sendMessage = useCallback(
    async (raw: string) => {
      const content = raw.trim()
      if (!content || sending || !token) return

      setSending(true)
      setError(null)
      setStreamingText('')

      let conversationId = activeId
      try {
        if (!conversationId) {
          const conversation = await api.createConversation(token)
          conversationId = conversation.id
          setConversations((prev) => [
            conversation,
            ...prev.filter((item) => item.id !== conversation.id),
          ])
          setActiveId(conversation.id)
        }

        const optimistic: Message = {
          id: -Date.now(),
          role: 'user',
          content,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, optimistic])
        setDraft('')

        await streamChat({
          token,
          conversationId,
          content,
          onEvent: (event) => {
            if (event.type === 'delta') {
              setStreamingText((prev) => prev + event.text)
            } else if (event.type === 'error') {
              setError(event.message)
            } else if (event.type === 'done' && event.message) {
              setMessages((prev) => [...prev, event.message as Message])
            }
          },
        })
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          logout()
          navigate('/login', { replace: true })
          return
        }
        setError(err instanceof Error ? err.message : '消息发送失败，请稍后再试')
      } finally {
        setSending(false)
        setStreamingText('')
        if (conversationId) {
          try {
            const [history, list] = await Promise.all([
              api.messages(token, conversationId),
              api.conversations(token),
            ])
            setMessages(history)
            setConversations(list)
          } catch {
            // keep the optimistic messages when the sync fails
          }
        }
      }
    },
    [activeId, logout, navigate, sending, token],
  )

  const activeConversation = conversations.find((item) => item.id === activeId)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  function handleConfirm() {
    setNotice('已确认（演示）')
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current)
    noticeTimer.current = window.setTimeout(() => setNotice(null), 2200)
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      <ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        user={user}
        open={sidebarOpen}
        disabled={sending}
        onSelect={(id) => void openConversation(id)}
        onNew={() => void createConversation()}
        onClose={() => setSidebarOpen(false)}
        onLogout={handleLogout}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line/80 px-4 md:px-6">
          <button
            onClick={() => setSidebarOpen(true)}
            className="grid size-9 place-items-center rounded-lg text-muted transition hover:bg-ink/5 hover:text-ink md:hidden"
          >
            <Menu className="size-[18px]" />
            <span className="sr-only">打开会话列表</span>
          </button>

          <div className="min-w-0 flex-1">
            <h1 className="truncate text-[14px] font-medium text-ink">
              {activeConversation?.title ?? '新对话'}
            </h1>
          </div>

          <span className="hidden items-center gap-1.5 rounded-full border border-line bg-white/70 px-2.5 py-1 text-[10.5px] text-muted sm:flex">
            <span
              className={cn(
                'size-1.5 rounded-full',
                health?.llm.mode === 'openai' ? 'bg-jade-500' : 'bg-amber-400',
              )}
            />
            {health ? (health.llm.mode === 'mock' ? '演示模式' : health.llm.model) : '连接中'}
          </span>

          <button
            onClick={() => setConfirmOpen(true)}
            title="安全确认演示"
            className="grid size-9 place-items-center rounded-lg border border-line bg-white text-muted transition hover:border-jade-200 hover:text-jade-700"
          >
            <ShieldCheck className="size-[16px]" />
            <span className="sr-only">安全确认演示</span>
          </button>
        </header>

        <div ref={scrollRef} className="scroll-thin flex-1 overflow-y-auto">
          {loadingMessages ? (
            <div className="grid h-full place-items-center">
              <LoaderCircle className="size-5 animate-spin text-muted/45" />
            </div>
          ) : messages.length === 0 && !sending ? (
            <EmptyState onPick={(text) => void sendMessage(text)} />
          ) : (
            <MessageList
              messages={messages}
              streamingText={streamingText}
              thinking={sending && !streamingText}
            />
          )}
        </div>

        <div className="shrink-0 px-4 pb-5 pt-2 md:px-6">
          {error && (
            <div
              aria-live="polite"
              className="mx-auto mb-2.5 flex w-full max-w-[760px] items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[12.5px] text-red-600"
            >
              <AlertCircle className="size-4 shrink-0" />
              {error}
            </div>
          )}

          <ChatComposer
            value={draft}
            onChange={setDraft}
            onSend={() => void sendMessage(draft)}
            disabled={sending}
          />

          <p className="mx-auto mt-2.5 max-w-[760px] text-center text-[10.5px] text-muted/45">
            AI 生成内容仅供参考，重要信息请以银行正式记录为准
          </p>
        </div>
      </div>

      <ActionConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        onConfirm={handleConfirm}
      />

      {notice && (
        <div className="rise-in fixed bottom-8 left-1/2 z-50 -translate-x-1/2 rounded-full bg-ink px-4 py-2 text-[12px] text-white shadow-lg">
          {notice}
        </div>
      )}
    </div>
  )
}
