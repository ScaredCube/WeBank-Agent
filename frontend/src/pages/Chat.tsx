import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { LayoutGroup, motion } from 'motion/react'

import { BankWorkspace, WorkspaceHeader } from '@/app/BankWorkspace'
import { initialWorkspacePanel } from '@/app/workspace-state'
import { ChatHome } from '@/components/chat/ChatHome'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { ConversationSidebar } from '@/components/chat/ConversationSidebar'
import { MessageList } from '@/components/chat/MessageList'
import { ConversationLoading } from '@/components/chat/ConversationLoading'
import { WorkspacePanel } from '@/features/workspace/WorkspacePanel'
import type { CardLossRecovery } from '@/features/actions/CardLossButton'
import { PendingActionDialog } from '@/features/actions/PendingActionDialog'
import { useChatController } from '@/features/chat/useChatController'
import { useAuth } from '@/lib/use-auth'
import type { StreamEvent } from '@/lib/sse'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import { cn } from '@/lib/utils'

type SourceNavigationFeedback = { type: 'status' | 'error'; message: string }
type SourceNavigation = {
  origin: CardOrigin
  status: 'opening' | 'located' | 'conversation-missing' | 'message-missing'
}

export function ChatPage() {
  const { token, user, logout } = useAuth()
  const navigate = useNavigate()

  const [actionWarning, setActionWarning] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [workspacePanel, setWorkspacePanel] = useState(initialWorkspacePanel)
  const [pendingAction, setPendingAction] = useState<Extract<StreamEvent, { type: 'action_required' }> | null>(null)
  const [actionOpen, setActionOpen] = useState(false)
  const [actionPreparing, setActionPreparing] = useState(false)
  const [cardLossRecovery, setCardLossRecovery] = useState<ReadonlyMap<number, CardLossRecovery>>(() => new Map())
  const [workspaceRevision, setWorkspaceRevision] = useState(0)
  const [privacyHidden, setPrivacyHidden] = useState(false)
  const [sourceNavigation, setSourceNavigation] = useState<SourceNavigation | null>(null)

  const [panelOpenedByUser, setPanelOpenedByUser] = useState(false)
  const onActionRequired = useCallback((event: Extract<StreamEvent, { type: 'action_required' }>) => { setPendingAction(event); setActionOpen(true) }, [])
  const onConversationChange = useCallback(() => setSidebarOpen(false), [])
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
  const { conversations, activeId, messages, draft, sending, receiving, streamingText, loadingMessages, historyUnavailable, creatingConversation, error, health, healthUnavailable, scrollRef, hasNewContent, onScroll, jumpToLatest, openConversation, createConversation, sendMessage, updateDraft, stopReceiving } = useChatController({ token, actionBlocked: actionPreparing || !!pendingAction, onActionRequired, onActionWarning: setActionWarning, onConversationChange })

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
  const composer = <ChatComposer
    value={draft}
    onChange={updateDraft}
    onSend={() => void sendMessage(draft)}
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
    <BankWorkspace sidebar={<ConversationSidebar
        conversations={conversations}
        activeId={activeId}
        user={user}
        open={sidebarOpen}
        activePanel={workspacePanel}
        hideActiveConversation={isHome && activeConversation?.title === '新对话'}
        disabled={sending || creatingConversation || actionPreparing || !!pendingAction}
        disabledReason={actionPreparing || pendingAction ? '请先处理当前操作，再切换或新建会话。' : undefined}
        newDisabled={loadingMessages}
        onSelect={(id) => { setSourceNavigation(null); void openConversation(id) }}
        onNew={() => { setSourceNavigation(null); void createConversation() }}
        onOpenPanel={(panel) => { setSourceNavigation(null); setPanelOpenedByUser(true); setWorkspacePanel(panel); setSidebarOpen(false) }}
        onClose={() => setSidebarOpen(false)}
        onLogout={handleLogout}
      />}
      panel={workspacePanel && token && user && <WorkspacePanel key={workspacePanel} token={token} userId={user.id} panel={workspacePanel} focusOnMount={panelOpenedByUser} hidden={privacyHidden} refreshSignal={workspaceRevision} actionDisabled={sending || actionPreparing || !!pendingAction} cardLossRecovery={cardLossRecovery} onCardLossRecoveryChange={onCardLossRecoveryChange} onCardLossResolved={onCardLossResolved} onActionBusy={setActionPreparing} onActionPrepared={(event) => { setPendingAction(event); setActionOpen(true) }} onTogglePrivacy={() => setPrivacyHidden((value) => !value)} onOpenSource={openSavedSource} sourceDisabled={sending || loadingMessages || creatingConversation || actionPreparing || !!pendingAction} onClose={() => setWorkspacePanel(null)} />}
      overlay={pendingAction && token && <PendingActionDialog key={pendingAction.action.id} event={pendingAction} token={token} open={actionOpen} hidden={privacyHidden} onTogglePrivacy={() => setPrivacyHidden((value) => !value)} onClose={() => setActionOpen(false)} onResolved={() => { if (pendingAction.action.action_type === 'card_loss' && typeof pendingAction.action.details.card_id === 'number') onCardLossRecoveryChange(pendingAction.action.details.card_id, null) }} onFinish={() => { setActionOpen(false); setPendingAction(null); setWorkspaceRevision((value) => value + 1) }} />}>
        <WorkspaceHeader title={activeConversation?.title ?? '新对话'} isHome={isHome} sidebarOpen={sidebarOpen} onOpenSidebar={() => setSidebarOpen(true)} hidden={privacyHidden} onTogglePrivacy={() => setPrivacyHidden((value) => !value)} status={
          <span className="hidden items-center gap-1.5 rounded-full border border-line bg-white/70 px-2.5 py-1 text-[10.5px] text-muted sm:flex">
            <span
              className={cn(
                'size-1.5 rounded-full',
                health?.llm.mode === 'openai' ? 'bg-jade-500' : 'bg-amber-400',
              )}
            />
            {health ? (health.llm.mode === 'mock' ? '演示模式' : health.llm.model) : healthUnavailable ? '状态不可用' : '连接中'}
          </span>}
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
              onPick={updateDraft}
              feedback={homeFeedback}
              disclaimer="AI 生成内容仅供参考，重要信息请以银行正式记录为准"
            />
          ) : (
            <MessageList
              messages={messages}
              streamingText={streamingText}
              thinking={sending && !streamingText}
              focusMessageId={sourceTarget?.conversationId === activeId ? sourceTarget.messageId : null}
              onFocusMessageResolved={onFocusMessageResolved}
            />
          )}
        </motion.div>

        {!isHome && <div className="shrink-0 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-2 md:px-6">
          {actionWarning && <div role="alert" className="mx-auto mb-2 flex w-full max-w-[680px] items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900"><span className="flex-1">{actionWarning}</span><button type="button" onClick={() => setActionWarning(null)} className="shrink-0 underline">已了解</button></div>}
          {pendingAction && !actionOpen && <button type="button" onClick={() => setActionOpen(true)} className="mx-auto mb-2 block w-full max-w-[680px] rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-left text-sm text-amber-900">查看待处理操作</button>}
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
