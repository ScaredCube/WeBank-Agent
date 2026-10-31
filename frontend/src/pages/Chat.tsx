import { useCallback, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Eye, EyeOff } from 'lucide-react'
import { LayoutGroup, motion } from 'motion/react'

import { BankWorkspace, WorkspaceHeader } from '@/app/BankWorkspace'
import { initialWorkspacePanel } from '@/app/workspace-state'
import { ChatHome, type ChatStarterPrompt } from '@/components/chat/ChatHome'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { ConversationSidebar } from '@/components/chat/ConversationSidebar'
import { MessageList } from '@/components/chat/MessageList'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import { billResultCard } from '@/features/intelligent-ui/bill-result-card'
import { CardStatusResult } from '@/features/intelligent-ui/CardStatusResult'
import { cardStatusSnapshotSchema } from '@/features/intelligent-ui/card-status-schema'
import { messageToolResults } from '@/features/intelligent-ui/tool-results'
import { ConversationLoading } from '@/components/chat/ConversationLoading'
import { WorkspacePanel } from '@/features/workspace/WorkspacePanel'
import type { CardLossRecovery } from '@/features/actions/CardLossButton'
import { PendingActionDialog } from '@/features/actions/PendingActionDialog'
import { PendingActionBanner } from '@/features/actions/PendingActionBanner'
import { useChatController } from '@/features/chat/useChatController'
import { useAuth } from '@/lib/use-auth'
import { api } from '@/lib/api'
import { useHomeAccountOverview } from '@/features/home/useHomeAccountOverview'
import type { StreamEvent } from '@/lib/sse'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import { cn } from '@/lib/utils'
import { addBankReference, type BankObjectReference } from '@/features/references/bank-object-reference'

type SourceNavigationFeedback = { type: 'status' | 'error'; message: string }
type SourceNavigation = {
  origin: CardOrigin
  status: 'opening' | 'located' | 'conversation-missing' | 'message-missing'
}

const bankingStarters: readonly ChatStarterPrompt[] = [
  { label: '查看本月收支', prompt: '请帮我查询本月账单，分析主要支出分类。', art: "chart" },
  { label: '检查订阅扣费', prompt: '帮我查看订阅与即将续费的项目，并识别可能的重复订阅。', art: "receipt" },
  { label: '准备一笔转账', prompt: '我想准备一笔转账，请帮我确认需要提供哪些信息。', art: "card" },
]

export function ChatPage() {
  const { token, user, logout } = useAuth()
  const navigate = useNavigate()

  const [actionWarning, setActionWarning] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false)
  const [workspacePanel, setWorkspacePanel] = useState(initialWorkspacePanel)
  const [pendingAction, setPendingAction] = useState<Extract<StreamEvent, { type: 'action_required' }> | null>(null)
  const [actionOpen, setActionOpen] = useState(false)
  const [actionPreparing, setActionPreparing] = useState(false)
  const [cardLossRecovery, setCardLossRecovery] = useState<ReadonlyMap<number, CardLossRecovery>>(() => new Map())
  const [workspaceRevision, setWorkspaceRevision] = useState(0)
  const referenceSearchCache = useRef<{key:string, promise:Promise<BankObjectReference[]>}|null>(null)
  const searchBankReferences = useCallback((): Promise<BankObjectReference[]> => {
    if (!token) return Promise.resolve([])
    const key = token + ':' + workspaceRevision
    if (referenceSearchCache.current?.key === key) return referenceSearchCache.current.promise
    // The catalog supplies display candidates only. Permission checks remain server-side.
    const promise = Promise.all([api.bankDashboard(token), api.cards(token)]).then(([dashboard,cards]) => [
      ...dashboard.accounts
        .filter(item => item.status === 'active' && item.currency === 'CNY')
        .map(item => ({kind:'account' as const,id:item.account_id,label:item.name,detail:item.masked_number})),
      ...cards
        .filter(item => item.account_status === 'active')
        .map(item => ({kind:'card' as const,id:item.card_id,label:item.account_name,detail:item.masked_number})),
      ...dashboard.contacts
        .filter(item => item.status === 'active')
        .map(item => ({kind:'contact' as const,id:item.contact_id,label:item.name,
          detail:item.bank_name + ' · ' + item.masked_phone})),
    ]).catch(error => {
      if (referenceSearchCache.current?.key === key) referenceSearchCache.current = null
      throw error
    })
    referenceSearchCache.current = {key,promise}
    return promise
  },[token,workspaceRevision])
  const [privacyHidden, setPrivacyHidden] = useState(false)
  const [referencesByConversation, setReferencesByConversation] = useState<Record<string, BankObjectReference[]>>({})
  const [sourceNavigation, setSourceNavigation] = useState<SourceNavigation | null>(null)

  const [panelOpenedByUser, setPanelOpenedByUser] = useState(false)
  const onActionRequired = useCallback((event: Extract<StreamEvent, { type: 'action_required' }>) => { setPendingAction(event); setActionOpen(true) }, [])
  const onConversationChange = useCallback(() => setSidebarOpen(false), [])
  const onConversationCreated = useCallback((id: number) => {
    setReferencesByConversation(current => {
      const selected = current.new
      if (!selected?.length) return current
      const next = {...current,[String(id)]:selected}
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
  const { conversations, activeId, messages, toolResultLists, draft, sending, receiving, streamingText, loadingMessages, historyUnavailable, creatingConversation, error, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving } = useChatController({ token, actionBlocked: actionPreparing || !!pendingAction, onActionRequired, onActionWarning: setActionWarning, onConversationChange, onConversationCreated })

  const referenceKey = String(activeId ?? 'new')
  const references = referencesByConversation[referenceKey] ?? []
  const addReference = useCallback((next: BankObjectReference) => {
    setReferencesByConversation(current => {
      const nextMap = {...current,[referenceKey]:addBankReference(current[referenceKey] ?? [],next)}
      if (referenceKey !== 'new') delete nextMap.new
      return nextMap
    })
    if (window.matchMedia?.('(max-width: 1279px)').matches) setWorkspacePanel(null)
  },[referenceKey])
  const removeReference = useCallback((value: BankObjectReference) => {
    setReferencesByConversation(current => ({...current,[referenceKey]:(current[referenceKey] ?? []).filter(item => !(item.id === value.id && item.kind === value.kind))}))
  },[referenceKey])

  const openSavedSource = useCallback((origin: CardOrigin) => {
    const sourceConversation = conversations.find((item) => item.id === origin.conversationId)
    if (!sourceConversation) {
      setSourceNavigation({ origin, status: 'conversation-missing' })
      setWorkspacePanel(null)
      return
    }

    setSourceNavigation({ origin, status: 'opening' })
    setWorkspacePanel(null)
    void openConversation(sourceConversation.id)
  }, [conversations, openConversation])

  const sourceMessageFound = !!sourceNavigation
    && sourceNavigation.origin.conversationId === activeId
    && !loadingMessages
    && !historyUnavailable
    && messages.some((message) => message.id === sourceNavigation.origin.messageId)
  const sourceTarget = sourceMessageFound ? sourceNavigation?.origin ?? null : null
  const sourceNavigationFeedback: SourceNavigationFeedback | null = (() => {
    if (!sourceNavigation) return null
    if (sourceNavigation.status === 'conversation-missing') return { type: 'error', message: '找不到收藏来源会话；它可能已删除或当前不可访问。' }
    if (sourceNavigation.status === 'message-missing') return { type: 'error', message: '找不到这条消息；来源会话中可能已删除或无法展示。' }
    if (sourceNavigation.origin.conversationId !== activeId || loadingMessages) return { type: 'status', message: '正在打开收藏来源…' }
    if (historyUnavailable) return { type: 'error', message: '无法读取收藏来源会话，请重试；来源消息尚未定位。' }
    if (!messages.some((message) => message.id === sourceNavigation.origin.messageId)) return { type: 'error', message: '找不到这条消息；来源会话中可能已删除或无法展示。' }
    if (sourceNavigation.status === 'located') return { type: 'status', message: '已定位到收藏的来源消息。' }
    return { type: 'status', message: '正在定位收藏中的来源消息…' }
  })()

  const onFocusMessageResolved = useCallback((messageId: number, found: boolean) => {
    setSourceNavigation((current) => {
      if (!current || current.origin.messageId !== messageId || current.origin.conversationId !== activeId) return current
      return { origin: current.origin, status: found ? 'located' : 'message-missing' }
    })
  }, [activeId])

  const activeConversation = conversations.find((item) => item.id === activeId)
  const isHome = messages.length === 0 && !sending && !loadingMessages && !historyUnavailable
  const homeOverview = useHomeAccountOverview(token, user?.id, isHome, workspaceRevision)
  const composer = <ChatComposer
    variant={isHome ? 'home' : 'conversation'}
    value={draft}
    onChange={updateDraft}
    onSend={() => void sendMessage(draft, references)}
    references={references}
    onReferenceDrop={addReference}
    onRemoveReference={removeReference}
    onSearchReferences={searchBankReferences}
    onStop={receiving ? stopReceiving : undefined}
    disabled={sending || creatingConversation || loadingMessages || historyUnavailable || actionPreparing || !!pendingAction}
  />
  const errorFeedback = error && (
    <div role="alert" className="mx-auto mt-4 flex w-full max-w-[680px] items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
      <AlertCircle className="size-4 shrink-0" />
      {error}
    </div>
  )
  const homeFeedback = (
    <>
      {actionWarning && (
        <div role="alert" className="mx-auto mt-4 flex w-full max-w-[680px] items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          <span className="flex-1">{actionWarning}</span>
          <button type="button" onClick={() => setActionWarning(null)} className="shrink-0 underline">已了解</button>
        </div>
      )}
      {errorFeedback}
    </>
  )

  function handleLogout() {
    setPendingAction(null)
    setCardLossRecovery(new Map())
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <BankWorkspace sidebarCollapsed={desktopSidebarCollapsed} sidebar={<ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        user={user}
        open={sidebarOpen}
        desktopCollapsed={desktopSidebarCollapsed}
        activePanel={workspacePanel}
        hideActiveConversation={isHome && activeConversation?.title === '新对话'}
        disabled={sending || creatingConversation || actionPreparing || !!pendingAction}
        disabledReason={actionPreparing || pendingAction ? '请先处理当前操作，再切换或新建会话。' : undefined}
        newDisabled={loadingMessages}
        onSelect={(id) => { setSourceNavigation(null); setWorkspacePanel(null); setPanelOpenedByUser(false); setSidebarOpen(false); void openConversation(id) }}
        onNew={() => { setSourceNavigation(null); void createConversation() }}
        onOpenPanel={(panel) => { setSourceNavigation(null); setPanelOpenedByUser(true); setWorkspacePanel(panel); setSidebarOpen(false) }}
        onToggleDesktopSidebar={() => setDesktopSidebarCollapsed((collapsed) => !collapsed)}
        onClose={() => setSidebarOpen(false)}
        onLogout={handleLogout}
      />}
      panel={workspacePanel && token && user && <WorkspacePanel key={workspacePanel} token={token} userId={user.id} panel={workspacePanel} focusOnMount={panelOpenedByUser} hidden={privacyHidden} refreshSignal={workspaceRevision} actionDisabled={sending || actionPreparing || !!pendingAction} cardLossRecovery={cardLossRecovery} onCardLossRecoveryChange={onCardLossRecoveryChange} onCardLossResolved={onCardLossResolved} onActionBusy={setActionPreparing} onActionPrepared={(event) => { setPendingAction(event); setActionOpen(true) }} onTogglePrivacy={() => setPrivacyHidden((value) => !value)} onOpenSource={openSavedSource} onReference={addReference} sourceDisabled={sending || loadingMessages || creatingConversation || actionPreparing || !!pendingAction} onClose={() => setWorkspacePanel(null)} />}
      overlay={pendingAction && token && <PendingActionDialog key={pendingAction.action.id} event={pendingAction} token={token} open={actionOpen} hidden={privacyHidden} onTogglePrivacy={() => setPrivacyHidden((value) => !value)} onClose={() => setActionOpen(false)} onResolved={() => { if (pendingAction.action.action_type === 'card_loss' && typeof pendingAction.action.details.card_id === 'number') onCardLossRecoveryChange(pendingAction.action.details.card_id, null) }} onFinish={() => { setActionOpen(false); setPendingAction(null); setWorkspaceRevision((value) => value + 1) }} />}>
        <WorkspaceHeader
          title={activeConversation?.title ?? '新对话'}
          isHome={isHome}
          sidebarOpen={sidebarOpen}
          onOpenSidebar={() => setSidebarOpen(true)}
          status={!isHome && <button type="button" onClick={() => setPrivacyHidden((value) => !value)}
            title={privacyHidden ? '显示金额' : '隐藏金额'}
            aria-label={privacyHidden ? '显示金额' : '隐藏金额'}
            aria-pressed={privacyHidden}
            className="grid size-10 place-items-center rounded-xl text-muted transition hover:bg-jade-50 hover:text-jade-800 focus-visible:outline-2 focus-visible:outline-jade-700">
            {privacyHidden ? <EyeOff size={17}/> : <Eye size={17}/>}
          </button>}
        />
        {healthUnavailable && <p role="status" className="border-b border-line bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:hidden">无法读取连接状态，仍可尝试发送。</p>}
        <p role="status" className="sr-only">{sending ? '消息请求进行中' : ''}</p>
        {sourceNavigationFeedback && <div role={sourceNavigationFeedback.type === 'error' ? 'alert' : 'status'} aria-live="polite" className={cn('flex shrink-0 items-start gap-3 border-b px-4 py-2.5 text-sm', sourceNavigationFeedback.type === 'error' ? 'border-red-200 bg-red-50 text-red-800' : 'border-jade-200 bg-jade-50 text-jade-900')}>
          <span className="flex-1">{sourceNavigationFeedback.message}</span>
          <button type="button" onClick={() => setSourceNavigation(null)} className="shrink-0 underline">已了解</button>
        </div>}

        <LayoutGroup id="bank-agent-chat-page">
        <motion.div ref={scrollRef} layoutScroll role={isHome ? undefined : 'log'} aria-label={isHome ? undefined : '对话消息'} aria-live="off" className="scroll-thin flex-1 overflow-y-auto" onScroll={onScroll}>
          {loadingMessages ? (
            <ConversationLoading />
          ) : historyUnavailable ? (
            <div className="grid h-full place-items-center px-6"><div className="text-center"><p className="text-sm text-muted">无法读取此会话，请重试。</p><button type="button" className="mt-4 rounded-xl border border-line bg-white px-4 py-2 text-sm text-jade-800" onClick={() => activeId ? void openConversation(activeId) : void createConversation()}>{activeId ? '重试加载会话' : '新建会话'}</button></div></div>
          ) : isHome ? (
            <ChatHome
              composer={composer}
              feedback={homeFeedback}
              suggestions={bankingStarters}
              onPick={updateDraft}
              overview={homeOverview}
              mode={workspacePanel ? 'sidecar' : 'full'}
              hidden={privacyHidden}
              onTogglePrivacy={() => setPrivacyHidden((value) => !value)}
              onOpenAssets={() => { setPanelOpenedByUser(true); setWorkspacePanel('assets') }}
              disclaimer="业务信息来自模拟银行环境，所有重要操作以服务端结果为准。"
            />
          ) : (
            <MessageList
              key={activeId ?? 'new'}
              scrollRoot={scrollRef}
              messages={messages}
              renderAfterMessage={(message) => {
                if (message.role !== 'assistant') return null
                const list = toolResultLists[message.id] ?? messageToolResults(message)
                if (list.length) return <div className="space-y-4">{list.map((result, index) => {
                  if (result.kind === 'monthly_bill') {
                    const card = billResultCard(result.data)
                    return card ? <IntelligentCard key={index} value={card} hidden={privacyHidden}/> : null
                  }
                  if (cardStatusSnapshotSchema.safeParse(result.data).success)
                    return <CardStatusResult key={index} value={result.data} hidden={privacyHidden}
                      onOpenAssets={() => { setPanelOpenedByUser(true); setWorkspacePanel('assets') }}/>
                  return null
                })}</div>
                return null
              }}
              streamingText={streamingText}
              thinking={sending && !streamingText}
              focusMessageId={sourceTarget?.conversationId === activeId ? sourceTarget.messageId : null}
              onFocusMessageResolved={onFocusMessageResolved}
            />
          )}
        </motion.div>

        {!isHome && <div className="shrink-0 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-2 md:px-6">
          {actionWarning && <div role="alert" className="mx-auto mb-2 flex w-full max-w-[680px] items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"><span className="flex-1">{actionWarning}</span><button type="button" onClick={() => setActionWarning(null)} className="shrink-0 underline">已了解</button></div>}
          {pendingAction && !actionOpen && <PendingActionBanner event={pendingAction} onOpen={() => setActionOpen(true)} />}
          {hasNewContent && (
            <button type="button" className="mx-auto mb-2 block rounded-full border border-line bg-white px-3 py-1 text-xs text-jade-800" onClick={jumpToLatest}>查看新消息</button>
          )}
          {error && (
            <div
              aria-live="polite"
              className="mx-auto mb-2.5 flex w-full max-w-[680px] items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[12.5px] text-red-600"
            >
              <AlertCircle className="size-4 shrink-0" />
              {error}
            </div>
          )}

          {composer}

          <p className="mx-auto mt-2.5 max-w-[680px] text-center text-[10.5px] text-muted/65">
            AI 生成内容仅供参考，重要信息请以银行正式记录为准
          </p>
        </div>}
        </LayoutGroup>
    </BankWorkspace>
  )
}
