import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, api, type Conversation, type Health, type Message } from '@/lib/api'
import { streamChat, type StreamEvent } from '@/lib/sse'
import { useConversationScroll } from './useConversationScroll'
import { savePendingChatRequest, clearPendingChatRequest, readPendingChatRequests } from './pending-request'
import { billResultCard } from '@/features/intelligent-ui/bill-result-card'
import { cardStatusSnapshotSchema } from '@/features/intelligent-ui/card-status-schema'
import { toolResultListSchema, type ToolResultItem } from '@/features/intelligent-ui/tool-results'
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
  const [toolResultLists, setToolResultLists] = useState<Record<number, ToolResultItem[]>>({})
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
  // Preserve the opaque request identity when a send is interrupted. An exact
  // retry in this mounted session must never create a second bank operation.
  const pendingRequest = useRef<{signature:string; requestId:string} | null>(null)
  const recoveryWarning = useRef(onActionWarning)
  useEffect(() => { recoveryWarning.current = onActionWarning }, [onActionWarning])

  // A reload only re-checks status. It never replays POST/tool calls.
  useEffect(() => {
    if (!token) return
    let cancelled = false
    const pending = readPendingChatRequests()
    void (async () => {
      for (const item of pending) {
        if (cancelled) return
        try {
          const status = await api.submissionStatus(token, item.conversationId, item.requestId)
          if (cancelled) return
          if (status.state === 'completed') {
            clearPendingChatRequest(item.requestId)
            recoveryWarning.current('上一条请求已完成，结果可在历史会话中查看。')
          } else if (status.state === 'action_pending') {
            clearPendingChatRequest(item.requestId)
            recoveryWarning.current('此前请求已创建待确认操作，请在操作记录中核对。不会再次执行或下发确认令牌。')
          } else {
            recoveryWarning.current('检测到尚未确认完成的历史请求，请先核对会话及操作记录，不要重复发起。')
          }
        } catch (error) {
          if (cancelled) return
          if (error instanceof ApiError && (error.status === 401 || error.status === 404)) {
            if (error.status === 404) clearPendingChatRequest(item.requestId)
          } else {
            recoveryWarning.current('历史请求状态暂时无法核对，请确认操作记录后再决定是否重新提交。')
          }
        }
      }
    })()
    return () => { cancelled = true }
  }, [token])

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
      const pendingToolResults: ToolResultItem[] = []
      let savedReply: Message | null = null
      let sessionExpired = false
      let sendFailure: string | null = null
      let actionWarningMessage: string | null = null
      let optimisticId: number | null = null
      let submittedRequestId: string | null = null
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

        const signature = JSON.stringify([conversationId, content, references.map(ref => [ref.kind, ref.id])])
        const requestId = pendingRequest.current?.signature === signature
          ? pendingRequest.current.requestId : crypto.randomUUID()
        pendingRequest.current = { signature, requestId }
        savePendingChatRequest({conversationId, requestId, createdAt: Date.now()})
        submittedRequestId = requestId
        let receivedDone = false

        const controller = new AbortController()
        receiveController.current = controller
        setReceiving(true)
        await streamChat({
          token,
          conversationId,
          content,
          references,
          requestId,
          signal: controller.signal,
          onEvent: (event) => {
            if (!isCurrent()) return
            if (event.type === 'bill_result') {
              if (billResultCard(event.data) && pendingToolResults.length < 8)
                pendingToolResults.push({kind:'monthly_bill',data:event.data})
            } else if (event.type === 'card_result') {
              const result = cardStatusSnapshotSchema.safeParse(event.data)
              if (result.success && pendingToolResults.length < 8)
                pendingToolResults.push({kind:'card_status',data:result.data})
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
            } else if (event.type === 'done') {
              receivedDone = true
              if (!event.message) return
              savedReply = event.message
              const validated = toolResultListSchema.safeParse(pendingToolResults)
              if (validated.success && validated.data.length) setToolResultLists(current => ({...current,[event.message!.id]:validated.data}))
              setMessages((prev) => [...prev, event.message as Message])
            }
          },
        })
        if (receivedDone) {
          pendingRequest.current = null
          clearPendingChatRequest(requestId)
        }
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
        if (isCurrent() && conversationId && submittedRequestId && !sessionExpired &&
            (sendFailure !== null || receiveController.current?.signal.aborted)) {
          try {
            const status = await api.submissionStatus(token, conversationId, submittedRequestId)
            if (status.state === 'completed') {
              savedReply = status.message
              sendFailure = null
              pendingRequest.current = null
              clearPendingChatRequest(submittedRequestId)
              setError(null)
            } else if (status.state === 'action_pending') {
              sendFailure = null
              pendingRequest.current = null
              clearPendingChatRequest(submittedRequestId)
              onActionWarning('待确认操作已在服务端创建。请到操作记录核对，原确认令牌不能重新获取。')
              setError(null)
            }
          } catch {
            // Lookup is optional; preserve the original uncertain-send warning.
          }
        }
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
  const renameConversation = useCallback(async (conversationId: number, title: string) => {
    if (!token || sending || actionBlocked) throw new Error('当前操作完成后才能修改会话名称')
    const renamed = await api.renameConversation(token, conversationId, title)
    setConversations(current => current.map(item => item.id === conversationId ? renamed : item))
  }, [token, sending, actionBlocked])

  function stopReceiving() { receiveController.current?.abort() }
  return { renameConversation, conversations, activeId, messages, toolResultLists, draft, sending, receiving, streamingText, loadingMessages, historyUnavailable, creatingConversation, error, health, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving }
}
