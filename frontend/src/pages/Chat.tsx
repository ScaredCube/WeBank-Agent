import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'

import { AppHeader, AppShell } from '@/app/AppShell'
import type { UtilityTabName } from '@/app/workspace-state'
import { ChatHome, type ChatStarterPrompt } from '@/components/chat/ChatHome'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { IntentCapsule } from '@/components/chat/IntentCapsule'
import { UtilitySidebar } from '@/components/chat/UtilitySidebar'
import { MessageList } from '@/components/chat/MessageList'
import { ConversationLoading } from '@/components/chat/ConversationLoading'
import { SaveBillCard } from '@/features/collections/SaveBillCard'
import { CollectionPanel } from '@/features/collections/CollectionPanel'
import { CardStatusResult } from '@/features/intelligent-ui/CardStatusResult'
import { InternalTransferResult } from '@/features/intelligent-ui/InternalTransferResult'
import { cardStatusSnapshotSchema } from '@/features/intelligent-ui/card-status-schema'
import { messageToolResults } from '@/features/intelligent-ui/tool-results'
import { AssetsPane } from '@/features/assets/AssetsPane'
import type { AssetIntent } from '@/features/assets/intent'
import { ActivityPane } from '@/features/workspace/ActivityPane'
import { PendingActionDialog } from '@/features/actions/PendingActionDialog'
import { PendingActionBanner } from '@/features/actions/PendingActionBanner'
import { CompletedActionCard } from '@/features/actions/CompletedActionCard'
import type { CardLossRecovery } from '@/features/actions/CardLossButton'
import { useChatController } from '@/features/chat/useChatController'
import { useAuth } from '@/lib/use-auth'
import { api, type BankCard, type BankDashboardData } from '@/lib/api'
import { PrivacyProvider, usePrivacy } from '@/features/privacy/PrivacyProvider'
import { DURATION, EASE_DRAWER, EASE_IN_OUT, EASE_OUT, useMotionReduced } from '@/lib/motion'
import type { ChatIntentPayload, StreamEvent } from '@/lib/sse'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import { addBankReference, type BankObjectReference } from '@/features/references/bank-object-reference'
import { cn } from '@/lib/utils'

type ActionEvent = Extract<StreamEvent, { type: 'action_required' }>
type SourceNavigation = { origin: CardOrigin; status: 'opening' | 'located' | 'conversation-missing' | 'message-missing' }

const bankingStarters: readonly ChatStarterPrompt[] = [
  { label: '查看本月收支', prompt: '请帮我查询本月账单，分析主要支出分类。', art: 'chart' },
  { label: '检查订阅扣费', prompt: '帮我查看订阅与即将续费的项目，并识别可能的重复订阅。', art: 'receipt' },
  { label: '准备一笔转账', prompt: '我想准备一笔转账，请帮我确认需要提供哪些信息。', art: 'card' },
]

function describeIntent(intent: AssetIntent): ChatIntentPayload {
  return {
    action: intent.action,
    source: { kind: intent.source.kind, id: intent.source.id },
    target: { kind: intent.target.kind, id: intent.target.id },
  }
}

function desktopViewport() {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(min-width: 1024px)').matches
}

export function ChatPage() {
  return <PrivacyProvider><ChatWorkspace /></PrivacyProvider>
}

function ChatWorkspace() {
  const { token, user, logout } = useAuth()
  const navigate = useNavigate()
  const privacy = usePrivacy()
  const reduced = useMotionReduced()
  const [compact, setCompact] = useState(() => !desktopViewport())

  const [assetsOpen, setAssetsOpen] = useState(desktopViewport)
  const [utilityOpen, setUtilityOpen] = useState(false)
  const [utilityTab, setUtilityTab] = useState<UtilityTabName>('conversations')
  const [actionWarning, setActionWarning] = useState<string | null>(null)
  const [pendingAction, setPendingAction] = useState<ActionEvent | null>(null)
  // Completed cards are attached to the assistant message of their turn, so
  // later messages never remove earlier results.
  const [completedByMessage, setCompletedByMessage] = useState<Record<number, ActionEvent[]>>({})
  const [actionOpen, setActionOpen] = useState(false)
  const [actionPreparing, setActionPreparing] = useState(false)
  const [cardLossRecovery, setCardLossRecovery] = useState<ReadonlyMap<number, CardLossRecovery>>(() => new Map())
  const [workspaceRevision, setWorkspaceRevision] = useState(0)
  const [intentCapsule, setIntentCapsule] = useState<AssetIntent | null>(null)
  // Only drafts from the active Chat submission can be edited after a
  // prepared action is safely cancelled. Direct asset actions lack this provenance.
  const lastSubmittedDraft = useRef<{ text: string; references: BankObjectReference[]; intent: AssetIntent | null } | null>(null)
  const [editablePendingDraft, setEditablePendingDraft] = useState<typeof lastSubmittedDraft.current>(null)
  const [referencesByConversation, setReferencesByConversation] = useState<Record<string, BankObjectReference[]>>({})
  const [sourceNavigation, setSourceNavigation] = useState<SourceNavigation | null>(null)
  const [dashboard, setDashboard] = useState<BankDashboardData | null>(null)
  const [cards, setCards] = useState<BankCard[]>([])
  const [assetsLoading, setAssetsLoading] = useState(false)
  const [dashboardError, setDashboardError] = useState<string | null>(null)
  const [cardError, setCardError] = useState<string | null>(null)
  const referenceSearchCache = useRef<{ key: string; promise: Promise<BankObjectReference[]> } | null>(null)
  const assetsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(min-width: 1024px)')
    const update = () => setCompact(!media.matches)
    update()
    media.addEventListener?.('change', update)
    return () => media.removeEventListener?.('change', update)
  }, [])

  const onActionRequired = useCallback((event: Extract<StreamEvent, { type: 'action_required' }>) => {
    setPendingAction(event)
    setEditablePendingDraft(lastSubmittedDraft.current)
    setActionOpen(true)
  }, [])
  const onConversationChange = useCallback(() => setUtilityOpen(false), [])
  const onConversationCreated = useCallback((id: number) => {
    setReferencesByConversation(current => {
      const selected = current.new
      if (!selected?.length) return current
      const next = { ...current, [String(id)]: selected }
      delete next.new
      return next
    })
  }, [])
  const onCardLossRecoveryChange = useCallback((cardId: number, recovery: CardLossRecovery | null) => {
    setCardLossRecovery((current) => {
      const next = new Map(current)
      if (recovery) next.set(cardId, recovery)
      else next.delete(cardId)
      return next
    })
  }, [])
  const onCardLossResolved = useCallback((cardId: number) => {
    onCardLossRecoveryChange(cardId, null)
    setWorkspaceRevision((value) => value + 1)
  }, [onCardLossRecoveryChange])

  const { renameConversation, conversations, activeId, messages, toolResultLists, draft, sending, receiving, streamingText, loadingMessages, loadingOlder, hasOlder, loadOlder, historyUnavailable, creatingConversation, error, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving } = useChatController({
    token, actionBlocked: actionPreparing || !!pendingAction, onActionRequired,
    onActionWarning: setActionWarning, onConversationChange, onConversationCreated,
  })

  // Keep a typed drag intent while the user edits or clears the composer.
  // Only a completed send that leaves no draft may remove it; clearing input
  // while editing must not silently unbind source and target entities.
  const wasSending = useRef(false)
  useEffect(() => {
    if (sending) {
      wasSending.current = true
      return
    }
    if (wasSending.current) {
      wasSending.current = false
      if (!draft.trim()) setIntentCapsule(null)
    }
  }, [sending, draft])

  const referenceKey = String(activeId ?? 'new')
  const references = referencesByConversation[referenceKey] ?? []

  const searchBankReferences = useCallback((): Promise<BankObjectReference[]> => {
    if (!token) return Promise.resolve([])
    const key = token + ':' + workspaceRevision
    if (referenceSearchCache.current?.key === key) return referenceSearchCache.current.promise
    const promise = Promise.all([api.bankDashboard(token), api.cards(token)]).then(([data, cardList]) => [
      ...data.accounts.filter(item => item.status === 'active' && item.currency === 'CNY')
        .map(item => ({ kind: 'account' as const, id: item.account_id, label: item.name, detail: item.masked_number })),
      ...cardList.filter(item => item.account_status === 'active')
        .map(item => ({ kind: 'card' as const, id: item.card_id, label: item.account_name, detail: item.masked_number })),
      ...data.contacts.filter(item => item.status === 'active')
        .map(item => ({ kind: 'contact' as const, id: item.contact_id, label: item.name, detail: item.bank_name + ' · ' + item.masked_phone })),
    ]).catch(error => {
      if (referenceSearchCache.current?.key === key) referenceSearchCache.current = null
      throw error
    })
    referenceSearchCache.current = { key, promise }
    return promise
  }, [token, workspaceRevision])

  const addReference = useCallback((next: BankObjectReference) => {
    setReferencesByConversation(current => ({ ...current, [referenceKey]: addBankReference(current[referenceKey] ?? [], next) }))
    if (!desktopViewport()) { setUtilityOpen(false); setAssetsOpen(false) }
  }, [referenceKey])
  const removeReference = useCallback((value: BankObjectReference) => {
    setReferencesByConversation(current => ({ ...current, [referenceKey]: (current[referenceKey] ?? []).filter(item => !(item.id === value.id && item.kind === value.kind)) }))
  }, [referenceKey])

  const refreshAssets = useCallback(() => setWorkspaceRevision((value) => value + 1), [])

  useEffect(() => {
    if (!token || !assetsOpen) return
    let cancelled = false
    setAssetsLoading(true); setDashboardError(null); setCardError(null)
    void Promise.allSettled([api.bankDashboard(token), api.cards(token)]).then(([dashboardResult, cardsResult]) => {
      if (cancelled) return
      if (dashboardResult.status === 'fulfilled') setDashboard(dashboardResult.value)
      else setDashboardError(dashboardResult.reason instanceof Error ? dashboardResult.reason.message : '账户与资产暂时无法读取。')
      if (cardsResult.status === 'fulfilled') setCards(cardsResult.value)
      else setCardError(cardsResult.reason instanceof Error ? cardsResult.reason.message : '银行卡暂时无法读取。')
      setAssetsLoading(false)
    })
    return () => { cancelled = true }
  }, [token, assetsOpen, workspaceRevision])

  // The mobile assets page is a full-screen overlay: keep Escape and focus
  // return local, while the desktop rail stays a plain column.
  useEffect(() => {
    if (!assetsOpen) return
    const compact = !desktopViewport()
    const previous = compact && document.activeElement instanceof HTMLElement ? document.activeElement : null
    const frame = compact
      ? requestAnimationFrame(() => {
          assetsRef.current?.querySelector<HTMLElement>('[data-assets-close]')?.focus()
        })
      : null
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape' && !desktopViewport()) setAssetsOpen(false)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      if (frame !== null) cancelAnimationFrame(frame)
      window.removeEventListener('keydown', onKeyDown)
      if (previous) queueMicrotask(() => { if (previous.isConnected) previous.focus() })
    }
  }, [assetsOpen])

  const openSavedSource = useCallback((origin: CardOrigin) => {
    const sourceConversation = conversations.find((item) => item.id === origin.conversationId)
    setUtilityOpen(false)
    if (!desktopViewport()) setAssetsOpen(false)
    if (!sourceConversation) {
      setSourceNavigation({ origin, status: 'conversation-missing' })
      return
    }
    setSourceNavigation({ origin, status: 'opening' })
    void openConversation(sourceConversation.id, origin.messageId)
  }, [conversations, openConversation])

  const sourceMessageFound = !!sourceNavigation
    && sourceNavigation.origin.conversationId === activeId
    && !loadingMessages && !historyUnavailable
    && messages.some((message) => message.id === sourceNavigation.origin.messageId)
  const sourceTarget = sourceMessageFound ? sourceNavigation?.origin ?? null : null
  const sourceNavigationFeedback = (() => {
    if (!sourceNavigation) return null
    if (sourceNavigation.status === 'conversation-missing') return { type: 'error' as const, message: '找不到收藏来源会话；它可能已删除或当前不可访问。' }
    if (sourceNavigation.status === 'message-missing') return { type: 'error' as const, message: '找不到这条消息；来源会话中可能已删除或无法展示。' }
    if (sourceNavigation.origin.conversationId !== activeId || loadingMessages) return { type: 'status' as const, message: '正在打开收藏来源…' }
    if (historyUnavailable) return { type: 'error' as const, message: '无法读取收藏来源会话，请重试；来源消息尚未定位。' }
    if (!messages.some((message) => message.id === sourceNavigation.origin.messageId)) return { type: 'error' as const, message: '找不到这条消息；来源会话中可能已删除或无法展示。' }
    return { type: 'status' as const, message: sourceNavigation.status === 'located' ? '已定位到收藏的来源消息。' : '正在定位收藏中的来源消息…' }
  })()

  const onFocusMessageResolved = useCallback((messageId: number, found: boolean) => {
    setSourceNavigation((current) => {
      if (!current || current.origin.messageId !== messageId || current.origin.conversationId !== activeId) return current
      return { origin: current.origin, status: found ? 'located' : 'message-missing' }
    })
  }, [activeId])

  const activeConversation = conversations.find((item) => item.id === activeId)
  const isHome = messages.length === 0 && !sending && !loadingMessages && !historyUnavailable

  function clearIntent() {
    if (intentCapsule && draft === intentCapsule.prefill) updateDraft('')
    setIntentCapsule(null)
  }

  function applyIntent(intent: AssetIntent) {
    setIntentCapsule(intent)
    setReferencesByConversation(current => ({ ...current, [referenceKey]: [] }))
    updateDraft(intent.prefill)
    setUtilityOpen(false)
    if (!desktopViewport()) setAssetsOpen(false)
    window.setTimeout(() => document.querySelector<HTMLTextAreaElement>('.chat-composer-input')?.focus(), 360)
  }

  function send() {
    if (!draft.trim()) return
    if (intentCapsule && draft.trim() === intentCapsule.prefill.trim()) {
      setActionWarning('拖拽已选定业务对象，请先填写实际金额；小We不会替你决定转账或交易金额。')
      return
    }
    const payload = intentCapsule ? describeIntent(intentCapsule) : undefined
    const text = draft
    const display = intentCapsule?.label
    lastSubmittedDraft.current = { text, references: [...references], intent: intentCapsule }
    void sendMessage(text, references, payload, display)
  }

  function openUtility(tab: UtilityTabName = 'conversations') {
    setUtilityTab(tab)
    setUtilityOpen(true)
  }

  function startNewConversation() {
    clearIntent()
    setSourceNavigation(null)
    setUtilityOpen(false)
    void createConversation()
  }

  const composer = <ChatComposer
    variant={isHome ? 'home' : 'conversation'}
    value={draft}
    onChange={updateDraft}
    onSend={send}
    references={references}
    onReferenceDrop={addReference}
    onRemoveReference={removeReference}
    onSearchReferences={searchBankReferences}
    onStop={receiving ? stopReceiving : undefined}
    intentSlot={intentCapsule ? <IntentCapsule intent={intentCapsule} onRemove={clearIntent} /> : undefined}
    intentActive={!!intentCapsule}
    disabled={sending || creatingConversation || loadingMessages || historyUnavailable || actionPreparing || !!pendingAction}
  />

  const errorFeedback = error && (
    <div role="alert" className="mx-auto mt-4 flex w-full max-w-[680px] items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
      <AlertCircle className="size-4 shrink-0" />{error}
    </div>
  )
  const homeFeedback = <>
    {actionWarning && <div role="alert" className="mx-auto mt-4 flex w-full max-w-[680px] items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"><span className="flex-1">{actionWarning}</span><button type="button" onClick={() => setActionWarning(null)} className="shrink-0 underline">已了解</button></div>}
    {errorFeedback}
  </>

  function handleLogout() {
    lastSubmittedDraft.current = null
    setEditablePendingDraft(null)
    setIntentCapsule(null); setPendingAction(null); setCompletedByMessage({}); setCardLossRecovery(new Map())
    setUtilityOpen(false); setAssetsOpen(false)
    logout(); navigate('/login', { replace: true })
  }

  const utility = token && user ? <UtilitySidebar
    tab={utilityTab}
    onTabChange={setUtilityTab}
    conversations={conversations}
    activeId={activeId}
    user={user}
    hideActiveConversation={isHome && activeConversation?.title === '新对话'}
    disabled={sending || creatingConversation || actionPreparing || !!pendingAction}
    disabledReason={actionPreparing || pendingAction ? '请先处理当前操作，再切换或新建会话。' : undefined}
    newDisabled={loadingMessages}
    collections={<CollectionPanel userId={user.id} hidden={privacy.hidden} token={token}
      onStartChat={() => { setUtilityOpen(false); updateDraft('请帮我查询本月账单，并生成一张消费分析卡片。') }}
      onOpenSource={openSavedSource}
      sourceDisabled={sending || loadingMessages || creatingConversation || actionPreparing || !!pendingAction} />}
    activity={<ActivityPane token={token} embedded />}
    onSelect={(id) => { clearIntent(); setSourceNavigation(null); setUtilityOpen(false); void openConversation(id) }}
    onNew={startNewConversation}
    onRename={renameConversation}
    onClose={() => setUtilityOpen(false)}
    onLogout={handleLogout}
  /> : null

  const assetsContent = token && <div className="h-full bg-workspace">
    <AssetsPane token={token} dashboard={dashboard} cards={cards} loading={assetsLoading}
      dashboardError={dashboardError} cardError={cardError}
      actionDisabled={sending || actionPreparing || !!pendingAction}
      cardLossRecovery={cardLossRecovery}
      onCardLossRecoveryChange={onCardLossRecoveryChange}
      onCardLossResolved={onCardLossResolved}
      onActionBusy={setActionPreparing}
      onActionPrepared={(event) => { setEditablePendingDraft(null); setPendingAction(event); setActionOpen(true) }}
      onIntent={applyIntent} onRetry={refreshAssets} onClose={() => setAssetsOpen(false)} />
  </div>

  const assetsPanel = token && assetsOpen ? <div ref={assetsRef} data-assets-panel
    onKeyDown={(event) => { if (event.key === 'Escape' && !desktopViewport()) setAssetsOpen(false) }}
    className="z-40 min-h-0 shrink-0 fixed inset-0 lg:static lg:inset-auto lg:z-auto lg:w-[340px] lg:border-r lg:border-line xl:w-[380px]">
    {assetsContent}
  </div> : null

  const assets = token ? (compact
    ? <AnimatePresence>
        {assetsOpen && <motion.div key="assets-overlay"
          className="fixed inset-0 z-30 bg-ink/30 backdrop-blur-[2px]"
          onClick={() => setAssetsOpen(false)} aria-hidden="true"
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={reduced ? { duration: 0 } : { duration: DURATION.base, ease: EASE_OUT }} />}
        {assetsOpen && <motion.div key="assets-panel" ref={assetsRef} data-assets-panel
          onKeyDown={(event) => { if (event.key === 'Escape') setAssetsOpen(false) }}
          className="z-40 min-h-0 shrink-0 fixed inset-0"
          initial={reduced ? false : { x: '-100%' }}
          animate={{ x: 0 }}
          exit={reduced
            ? { opacity: 0, transition: { duration: 0 } }
            : { x: '-100%', transition: { duration: DURATION.base, ease: EASE_IN_OUT } }}
          transition={reduced ? { duration: 0 } : { duration: DURATION.drawer, ease: EASE_DRAWER }}>
          {assetsContent}
        </motion.div>}
      </AnimatePresence>
    : assetsPanel) : null

  return <AppShell assets={assets} utility={utility} utilityOpen={utilityOpen && !!utility} onCloseUtility={() => setUtilityOpen(false)}>
    <AppHeader title={activeConversation?.title ?? '新对话'} isHome={isHome}
      assetsOpen={assetsOpen} onToggleAssets={() => setAssetsOpen((open) => !open)}
      onNewConversation={startNewConversation}
      newConversationDisabled={sending || creatingConversation || actionPreparing || !!pendingAction || loadingMessages}
      utilityOpen={utilityOpen} onOpenUtility={() => openUtility()} />
    {healthUnavailable && <p role="status" className="border-b border-line bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:hidden">无法读取连接状态，仍可尝试发送。</p>}
    {sourceNavigationFeedback && <div role={sourceNavigationFeedback.type === 'error' ? 'alert' : 'status'} aria-live="polite" className={cn('flex shrink-0 items-start gap-3 border-b px-4 py-2.5 text-sm', sourceNavigationFeedback.type === 'error' ? 'border-red-200 bg-red-50 text-red-800' : 'border-jade-200 bg-jade-50 text-jade-900')}>
      <span className="flex-1">{sourceNavigationFeedback.message}</span>
      <button type="button" onClick={() => setSourceNavigation(null)} className="shrink-0 underline">已了解</button>
    </div>}

    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} role={isHome ? undefined : 'log'} aria-label={isHome ? undefined : '对话消息'} aria-live="off" className="scroll-thin flex-1 overflow-y-auto" onScroll={onScroll}>
        {loadingMessages ? <ConversationLoading />
          : historyUnavailable ? <div className="grid h-full place-items-center px-6"><div className="text-center"><p className="text-sm text-muted">无法读取此会话，请重试。</p><button type="button" className="mt-4 rounded-xl border border-line bg-white px-4 py-2 text-sm text-jade-800" onClick={() => activeId ? void openConversation(activeId) : void createConversation()}>{activeId ? '重试加载会话' : '新建会话'}</button></div></div>
          : isHome ? <ChatHome composer={composer} feedback={homeFeedback} suggestions={bankingStarters} onPick={updateDraft}
              disclaimer="业务信息来自模拟银行环境，所有重要操作以服务端结果为准。" />
          : <MessageList key={activeId ?? 'new'} scrollRoot={scrollRef} messages={messages} hasOlder={hasOlder} loadingOlder={loadingOlder}
              onLoadOlder={() => void loadOlder()}
              renderAfterMessage={(message) => {
                if (message.role !== 'assistant') return null
                const list = toolResultLists[message.id] ?? messageToolResults(message)
                const completed = completedByMessage[message.id] ?? []
                if (!list.length && !completed.length) return null
                return <motion.div className="space-y-4"
                  initial={reduced ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={reduced ? { duration: 0 } : { duration: DURATION.base, ease: EASE_OUT }}>
                  {list.map((result, index) => {
                  if (result.kind === 'monthly_bill') {
                    return token && user && activeId && message.id > 0
                      ? <SaveBillCard key={`${message.id}-${index}`} value={result.data} hidden={privacy.hidden} userId={user.id} token={token} origin={{ conversationId: activeId, messageId: message.id }} />
                      : null
                  }
                  if (result.kind === 'internal_transfer') return <InternalTransferResult key={`${message.id}-${index}`} value={result.data} />
                  if (cardStatusSnapshotSchema.safeParse(result.data).success)
                    return <CardStatusResult key={index} value={result.data} hidden={privacy.hidden} onOpenAssets={() => setAssetsOpen(true)} />
                  return null
                })}
                {completed.map((event, index) => <CompletedActionCard key={`${message.id}-completed-${event.action.id}-${index}`} event={event} />)}
                </motion.div>
              }}
              streamingText={streamingText} thinking={sending && !streamingText}
              focusMessageId={sourceTarget?.conversationId === activeId ? sourceTarget.messageId : null}
              onFocusMessageResolved={onFocusMessageResolved} />
        }
      </div>

      {!isHome && <div className="shrink-0 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-2 md:px-6">
        {actionWarning && <div role="alert" className="mx-auto mb-2 flex w-full max-w-[680px] items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"><span className="flex-1">{actionWarning}</span><button type="button" onClick={() => setActionWarning(null)} className="shrink-0 underline">已了解</button></div>}
        {pendingAction && !actionOpen && <PendingActionBanner event={pendingAction} onOpen={() => setActionOpen(true)} />}
        {hasNewContent && <button type="button" className="mx-auto mb-2 block rounded-full border border-line bg-white px-3 py-1 text-xs text-jade-800" onClick={jumpToLatest}>查看新消息</button>}
        {errorFeedback}
        {composer}
        <p className="mx-auto mt-2.5 max-w-[680px] text-center text-[10.5px] text-muted/65">AI 生成内容仅供参考，重要信息请以银行正式记录为准</p>
      </div>}
    </div>

    {pendingAction && token && <PendingActionDialog key={pendingAction.action.id} event={pendingAction} token={token} open={actionOpen} hidden={privacy.hidden} onTogglePrivacy={privacy.toggle}
      onClose={() => setActionOpen(false)}
      onEdit={editablePendingDraft ? () => {
        // The dialog only calls this after the old server action is cancelled.
        // Restore both the user's text and the typed object bindings.
        setActionOpen(false)
        setPendingAction(null)
        setEditablePendingDraft(null)
        setIntentCapsule(editablePendingDraft.intent)
        setReferencesByConversation(current => ({ ...current, [referenceKey]: editablePendingDraft.references }))
        updateDraft(editablePendingDraft.text)
        setActionWarning('原待确认操作已取消。请修改信息后重新发送，系统将重新核验并准备新操作。')
        window.requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.chat-composer-input')?.focus())
      } : undefined}
      onResolved={(status) => {
        if (pendingAction.action.action_type === 'card_loss' && typeof pendingAction.action.details.card_id === 'number') onCardLossRecoveryChange(pendingAction.action.details.card_id, null)
        if (status === 'completed') {
          const latestAssistant = [...messages].reverse().find((message) => message.role === 'assistant' && message.id > 0)
          if (latestAssistant) {
            setCompletedByMessage((current) => {
              const existing = current[latestAssistant.id] ?? []
              return {
                ...current,
                [latestAssistant.id]: [
                  ...existing.filter((entry) => entry.action.id !== pendingAction.action.id),
                  pendingAction,
                ],
              }
            })
          }
          refreshAssets()
          window.requestAnimationFrame(() => {
            const root = scrollRef.current
            if (root && typeof root.scrollTo === 'function') root.scrollTo({ top: root.scrollHeight, behavior: 'auto' })
            else if (root) root.scrollTop = root.scrollHeight
          })
        }
      }}
      onFinish={() => { lastSubmittedDraft.current = null; setActionOpen(false); setPendingAction(null); setEditablePendingDraft(null); refreshAssets() }} />}
  </AppShell>
}
