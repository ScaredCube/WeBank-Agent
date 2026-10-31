import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type Conversation, type Health, type Message } from '@/lib/api'
import { streamChat, type StreamEvent } from '@/lib/sse'
import { useConversationScroll } from './useConversationScroll'
import { billResultCard } from '@/features/intelligent-ui/bill-result-card'
import type { CardDescription } from '@/features/intelligent-ui/schema'
import { composeReferenceContext, type BankObjectReference } from '@/features/references/bank-object-reference'

type ActionEvent = Extract<StreamEvent, { type: 'action_required' }>

function restoreDraftBefore(current: string, content: string): string {
  if (!current) return content
  if (current === content || current.startsWith(`${content}\n`)) return current
  return `${content}\n${current}`
}

export function useChatController({ token, actionBlocked, onActionRequired, onActionWarning, onConversationChange, onConversationCreated }: {
  token: string | null
  actionBlocked: boolean
  onActionRequired: (event: ActionEvent) => void
  onActionWarning: (message: string) => void
  onConversationChange: () => void
  onConversationCreated?: (conversationId: number) => void
}) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [resultCards, setResultCards] = useState<Record<number, CardDescription>>({})
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [receiving, setReceiving] = useState(false)
  const [streamingText, setStreamingText] = useState('')
  const [loadingMessages, setLoadingMessages] = useState(true)
  const [historyUnavailable, setHistoryUnavailable] = useState(false)
  const [creatingConversation, setCreatingConversation] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthUnavailable, setHealthUnavailable] = useState(false)
  const { scrollRef, hasNewContent, onScroll, resetScroll, jumpToLatest } = useConversationScroll(messages, streamingText, sending, loadingMessages)
  const sendingRef = useRef(false)
  const receiveController = useRef<AbortController | null>(null)
  const creatingRef = useRef(false)
  const draftDuringCreation = useRef('')
  const historyRequest = useRef(0)
  const sessionGeneration = useRef(0)
  const drafts = useRef(new Map<number | null, string>())

  useEffect(() => {
    if (!token) return
    let cancelled = false
    api
      .health()
      .then((result) => { if (!cancelled) { setHealth(result); setHealthUnavailable(false) } })
      .catch(() => { if (!cancelled) { setHealth(null); setHealthUnavailable(true) } })
    return () => { cancelled = true }
  }, [token])

  useEffect(() => {
    const generationRef = sessionGeneration
    const historyRef = historyRequest
    const streamRef = receiveController
    generationRef.current++
    return () => {
      generationRef.current++
      historyRef.current++
      streamRef.current?.abort()
    }
  }, [token])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    const requestId = ++historyRequest.current

    void (async () => {
      try {
        const list = await api.conversations(token)
        if (cancelled || requestId !== historyRequest.current) return
        setConversations(list)
        if (list.length > 0) {
          const first = list[0]
          setActiveId(first.id)
          const history = await api.messages(token, first.id)
          if (!cancelled && requestId === historyRequest.current) setMessages(history)
        }
      } catch (err) {
        if (!cancelled && requestId === historyRequest.current) { setHistoryUnavailable(true); setError(err instanceof Error ? err.message : '会话加载失败') }
      } finally {
        if (!cancelled && requestId === historyRequest.current) setLoadingMessages(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [token])

  const openConversation = useCallback(
    async (id: number) => {
      if (sending || actionBlocked || !token) return
      if (id === activeId && !historyUnavailable) return
      const requestId = ++historyRequest.current
      drafts.current.set(activeId, draft)
      setDraft(drafts.current.get(id) ?? '')
      onConversationChange()
      resetScroll('top')
      setActiveId(id)
      setMessages([])
      setHistoryUnavailable(false)
      setError(null)
      setLoadingMessages(true)
      try {
        const history = await api.messages(token, id)
        if (requestId === historyRequest.current) {
          setMessages(history)
          setStreamingText('')
        }
      } catch (err) {
        if (requestId === historyRequest.current) { setHistoryUnavailable(true); setError(err instanceof Error ? err.message : '会话加载失败') }
      } finally {
        if (requestId === historyRequest.current) setLoadingMessages(false)
      }
    },
    [activeId, draft, sending, actionBlocked, token, historyUnavailable, resetScroll, onConversationChange],
  )

  const createConversation = useCallback(async () => {
    if (sending || actionBlocked || loadingMessages || creatingRef.current || !token) return
    creatingRef.current = true
    setCreatingConversation(true)
    const requestId = ++historyRequest.current
    draftDuringCreation.current = draft
    drafts.current.set(activeId, draft)
    try {
      const conversation = await api.createConversation(token)
      if (requestId !== historyRequest.current) return
      drafts.current.set(activeId, draftDuringCreation.current)
      setConversations((prev) => [conversation, ...prev])
      setActiveId(conversation.id)
      onConversationCreated?.(conversation.id)
      resetScroll('top')
      setMessages([])
      setHistoryUnavailable(false)
      setDraft('')
      setLoadingMessages(false)
      setError(null)
      onConversationChange()
    } catch (err) {
      if (requestId === historyRequest.current) {
        setLoadingMessages(false)
        setError(err instanceof Error ? err.message : '新建会话失败')
      }
    } finally {
      creatingRef.current = false
      setCreatingConversation(false)
    }
  }, [activeId, draft, loadingMessages, sending, actionBlocked, token, resetScroll, onConversationChange, onConversationCreated])

  const sendMessage = useCallback(
    async (raw: string, references: BankObjectReference[] = []) => {
      const content = composeReferenceContext(raw, references)
      if (!content || sendingRef.current || sending || creatingRef.current || loadingMessages || historyUnavailable || actionBlocked || !token) return

      sendingRef.current = true
      setSending(true)
      resetScroll()
      setError(null)
      setStreamingText('')

      let conversationId = activeId
      let receivedText = ''
      let pendingBill: CardDescription | null = null
      let savedReply: Message | null = null
      let sessionExpired = false
      let sendFailure: string | null = null
      let actionWarningMessage: string | null = null
      let optimisticId: number | null = null
      const generation = sessionGeneration.current
      const isCurrent = () => sessionGeneration.current === generation
      const previousMessageIds = new Set(messages.map((item) => item.id))
      try {
        if (!conversationId) {
          const conversation = await api.createConversation(token)
          if (!isCurrent()) return
          conversationId = conversation.id
          setConversations((prev) => [
            conversation,
            ...prev.filter((item) => item.id !== conversation.id),
          ])
          setActiveId(conversation.id)
          onConversationCreated?.(conversation.id)
        }

        const optimistic: Message = {
          id: -Date.now(),
          role: 'user',
          content,
          created_at: new Date().toISOString(),
        }
        optimisticId = optimistic.id
        setMessages((prev) => [...prev, optimistic])
        if (raw === draft) setDraft((current) => current.startsWith(raw) ? current.slice(raw.length) : current)
        drafts.current.delete(conversationId)

        const controller = new AbortController()
        receiveController.current = controller
        setReceiving(true)
        await streamChat({
          token,
          conversationId,
          content,
          references,
          signal: controller.signal,
          onEvent: (event) => {
            if (!isCurrent()) return
            if (event.type === 'bill_result') {
              pendingBill = billResultCard(event.data)
            } else if (event.type === 'delta') {
              receivedText += event.text
              setStreamingText((prev) => prev + event.text)
            } else if (event.type === 'error') {
              sendFailure = event.message || '服务器返回错误'
              setError(sendFailure)
            } else if (event.type === 'action_warning') {
              actionWarningMessage = event.message
              onActionWarning(event.message)
            } else if (event.type === 'action_required') {
              onActionRequired(event)
            } else if (event.type === 'done' && event.message) {
              savedReply = event.message
              if (pendingBill) setResultCards(current => ({...current,[event.message!.id]:pendingBill!}))
              setMessages((prev) => [...prev, event.message as Message])
            }
          },
        })
      } catch (err) {
        if (!isCurrent()) return
        if (receiveController.current?.signal.aborted) {
          setError('已停止接收，服务端可能仍在处理。请查看历史记录，不要盲目重复操作。')
        } else {
          if (err instanceof ApiError && err.status === 401) {
            sessionExpired = true
            return
          }
          if (err instanceof ApiError && (err.status === 422 || err.status === 400)) {
            setDraft((current) => restoreDraftBefore(current, raw))
            if (optimisticId !== null) setMessages((previous) => previous.filter((message) => message.id !== optimisticId))
            setError(err.message)
          } else {
            sendFailure = err instanceof Error && err.message ? err.message : '消息发送失败'
            setError(sendFailure)
          }
        }
      } finally {
        if (isCurrent()) {
          receiveController.current = null
          setReceiving(false)
          setStreamingText('')
        }
        if (isCurrent() && conversationId && !sessionExpired) {
          try {
            const [history, list] = await Promise.all([
              api.messages(token, conversationId),
              api.conversations(token),
            ])
            if (isCurrent() && receivedText && !savedReply) {
              const matchingHistory = history.some((item) => item.role === 'assistant' && !previousMessageIds.has(item.id) && item.content.startsWith(receivedText))
              setMessages(matchingHistory ? history : [...history, { id: -Date.now(), role: 'assistant', content: receivedText, created_at: new Date().toISOString() }])
              setError((current) => current ?? (matchingHistory ? '历史中出现相同片段，请核对回复。' : '本条回复未确认保存到历史，刷新后可能无法恢复。'))
            } else if (isCurrent()) {
              const received = savedReply as Message | null
              if (received && !history.some((item) => item.id === received.id)) {
                setMessages([...history, received])
                setError((current) => current ?? '历史记录暂未包含本条回复，已保留当前内容。')
              } else setMessages(history)
            }
            if (isCurrent()) setConversations(list)
            if (isCurrent() && sendFailure !== null) {
              setDraft((current) => restoreDraftBefore(current, raw))
              const possibleMatch = history.some((item) => item.role === 'user' && !previousMessageIds.has(item.id) && item.content === content)
              const warning = possibleMatch
                ? '历史中出现了同文用户消息，可能已通过本次请求发送；客户端无法确认来源。原文已保留在输入框。请先核对历史记录，再决定是否重发。'
                : '发送结果暂不确定，原文已保留在输入框。请先核对历史记录，再决定是否重发。'
              onActionWarning(actionWarningMessage ? `${actionWarningMessage} ${warning}` : warning)
              setError(sendFailure)
            }
          } catch {
            if (isCurrent() && sendFailure !== null) {
              setDraft((current) => restoreDraftBefore(current, raw))
              const warning = '发送结果暂不确定，历史记录也暂时无法核对。原文已保留在输入框；请稍后核对历史后再决定是否重发。'
              onActionWarning(actionWarningMessage ? `${actionWarningMessage} ${warning}` : warning)
              setError(sendFailure)
            }
            if (isCurrent() && receivedText && !savedReply) {
              setMessages((previous) => [...previous, { id: -Date.now(), role: 'assistant', content: receivedText, created_at: new Date().toISOString() }])
              setError((current) => current ?? '本条回复未确认保存，刷新后可能无法恢复。')
            }
          }
        }
        if (isCurrent()) { sendingRef.current = false; setSending(false) }
      }
    },
    [activeId, actionBlocked, draft, historyUnavailable, loadingMessages, messages, sending, token, resetScroll, onActionRequired, onActionWarning, onConversationCreated],
  )

  function updateDraft(value: string) {
    if (creatingRef.current) draftDuringCreation.current = value
    setDraft(value)
  }
  function stopReceiving() { receiveController.current?.abort() }
  return { conversations, activeId, messages, resultCards, draft, sending, receiving, streamingText, loadingMessages, historyUnavailable, creatingConversation, error, health, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving }
}
