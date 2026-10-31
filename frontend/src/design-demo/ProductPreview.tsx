import { useCallback, useRef, useState } from 'react'
import { ArrowLeftRight, BookmarkPlus, CalendarDays, CreditCard } from 'lucide-react'
import { LayoutGroup, motion } from 'motion/react'
import { BankWorkspace, WorkspaceHeader } from '@/app/BankWorkspace'
import { initialWorkspacePanel } from '@/app/workspace-state'
import { ConversationSidebar } from '@/components/chat/ConversationSidebar'
import { ChatHome, type ChatStarterPrompt } from '@/components/chat/ChatHome'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { MessageList } from '@/components/chat/MessageList'
import { ConversationLoading } from '@/components/chat/ConversationLoading'
import { IntelligentCard } from '@/features/intelligent-ui/Renderer'
import type { CardOrigin } from '@/features/intelligent-ui/schema'
import { CollectionPanel } from '@/features/collections/CollectionPanel'
import { saveSnapshot } from '@/features/collections/store'
import { PendingActionDialog } from '@/features/actions/PendingActionDialog'
import type { ActionTransport } from '@/features/actions/transport'
import { WorkspacePanelFrame } from '@/features/workspace/WorkspacePanelFrame'
import { ActivityList } from '@/features/workspace/ActivityList'
import { useConversationScroll } from '@/features/chat/useConversationScroll'
import type { TransferIntent } from '@/features/assets/intent'
import type { Conversation, Message } from '@/lib/api'
import type { StreamEvent } from '@/lib/sse'
import { PreviewAssets } from './PreviewAssets'
import { createPreviewActionTransport, makePreviewAction, previewActivity, previewCardMessageIds, previewCards, previewConversations, previewMessages } from './scenarios'

const previewDatabase = 'webank-ui-preview-snapshots'
const emptyMessages: Message[] = []
type PreviewScenario = 'normal' | 'empty' | 'error' | 'loading'

const previewSuggestions = [
  { label: '查一下我的账户余额', prompt: '查一下我的账户余额', icon: CreditCard },
  { label: '看看这个月的消费', prompt: '看看这个月的消费', icon: CalendarDays },
  { label: '准备给朋友转账', prompt: '准备给朋友转账', icon: ArrowLeftRight },
] satisfies readonly ChatStarterPrompt[]

interface InitialPreviewState {
  scenario: PreviewScenario
  activeId: number
  nextConversationId: number
  conversations: Conversation[]
}

function PreviewScenarioSelect({ scenario, onChange, mobile = false }: {
  scenario: PreviewScenario
  onChange: (scenario: PreviewScenario) => void
  mobile?: boolean
}) {
  return (
    <select
      aria-label={mobile ? '手机预览状态' : '选择预览状态'}
      value={scenario}
      onChange={(event) => onChange(event.target.value as PreviewScenario)}
      className={mobile
        ? 'rounded-md border border-line bg-white px-1.5 py-0.5 text-[11px] text-ink'
        : 'rounded-md border border-jade-200 bg-white px-1 py-0.5 text-xs'}
    >
      <option value="normal">正常</option>
      <option value="empty">空状态</option>
      <option value="loading">加载中</option>
      <option value="error">异常</option>
    </select>
  )
}

function PreviewStatus({ scenario, onChange }: {
  scenario: PreviewScenario
  onChange: (scenario: PreviewScenario) => void
}) {
  return (
    <div title="合成数据，不连接 Agent 或业务接口" className="ml-auto hidden shrink-0 items-center gap-2 rounded-full bg-jade-50 px-2.5 py-1 text-xs text-jade-800 sm:flex">
      <span>合成预览</span>
      <PreviewScenarioSelect scenario={scenario} onChange={onChange} />
    </div>
  )
}

function MobilePreviewStatus({ scenario, onChange }: {
  scenario: PreviewScenario
  onChange: (scenario: PreviewScenario) => void
}) {
  return (
    <div title="合成数据，不连接 Agent 或业务接口" className="flex h-8 shrink-0 items-center justify-center gap-2 border-b border-line/70 bg-white/45 px-3 text-[10.5px] text-muted sm:hidden">
      <span>合成数据 · 不连接 Agent 或业务接口</span>
      <PreviewScenarioSelect mobile scenario={scenario} onChange={onChange} />
    </div>
  )
}

function getInitialPreview(): InitialPreviewState {
  const requested = new URLSearchParams(window.location.search).get('state')
  const scenario = requested === 'empty' || requested === 'error' || requested === 'loading' ? requested : 'normal'
  if (scenario === 'empty') {
    const createdAt = new Date().toISOString()
    return {
      scenario,
      activeId: 4,
      nextConversationId: 5,
      conversations: [{ id: 4, title: '新对话', created_at: createdAt, updated_at: createdAt }, ...previewConversations],
    }
  }
  return { scenario, activeId: 1, nextConversationId: 4, conversations: previewConversations }
}

export default function ProductPreview() {
  const [initialPreview] = useState(getInitialPreview)
  const [conversations, setConversations] = useState(initialPreview.conversations)
  const [activeId, setActiveId] = useState(initialPreview.activeId)
  const [messages, setMessages] = useState<Record<number, Message[]>>(previewMessages)
  const [drafts, setDrafts] = useState<Record<number, string>>({})
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [desktopSidebarCollapsed, setDesktopSidebarCollapsed] = useState(false)
  const [panel, setPanel] = useState(initialWorkspacePanel)
  const [hidden, setHidden] = useState(false)
  const [saving, setSaving] = useState(false)
  const [scenario, setScenario] = useState<PreviewScenario>(initialPreview.scenario)
  const [previewAction, setPreviewAction] = useState<{ transport: ActionTransport; event: Extract<StreamEvent, { type: 'action_required' }> } | null>(null)
  const [notice, setNotice] = useState('')
  const [sourceError, setSourceError] = useState('')
  const [sourceTarget, setSourceTarget] = useState<CardOrigin | null>(null)
  const [intents, setIntents] = useState<Record<number, TransferIntent | undefined>>({})
  const nextMessageId = useRef(100)
  const nextConversationId = useRef(initialPreview.nextConversationId)
  const [panelOpenedByUser, setPanelOpenedByUser] = useState(false)
  const currentCard = scenario === 'normal' ? previewCards[activeId] : undefined
  const currentMessages = scenario === 'normal' ? (messages[activeId] ?? emptyMessages) : emptyMessages
  const isHome = scenario === 'empty' || (scenario === 'normal' && currentMessages.length === 0)
  const canCompose = scenario === 'normal' || scenario === 'empty'
  const { scrollRef, onScroll, resetScroll, hasNewContent, jumpToLatest } = useConversationScroll(currentMessages, '', false, false)

  function send() {
    const content = drafts[activeId]?.trim()
    if (!content || !canCompose) return
    setSourceTarget(null)
    const createdAt = new Date().toISOString()
    const shouldStartConversation = scenario === 'empty' && (messages[activeId]?.length ?? 0) > 0
    const conversationId = shouldStartConversation ? nextConversationId.current++ : activeId
    if (shouldStartConversation) {
      setConversations((current) => [{ id: conversationId, title: content.slice(0, 28), created_at: createdAt, updated_at: createdAt }, ...current])
      setActiveId(conversationId)
      resetScroll()
    } else {
      setConversations((current) => current.map((item) => item.id === conversationId && item.title === '新对话'
        ? { ...item, title: content.slice(0, 28), updated_at: createdAt }
        : item))
    }
    const id = nextMessageId.current
    nextMessageId.current += 2
    setMessages((current) => ({
      ...current,
      [conversationId]: [
        ...(scenario === 'normal' ? current[conversationId] ?? [] : []),
        { id, role: 'user', content, created_at: createdAt },
        { id: id + 1, role: 'assistant', content: '这是合成预览，消息不会发送给 Agent。', created_at: createdAt },
      ],
    }))
    setDrafts((current) => ({ ...current, [activeId]: '', [conversationId]: '' }))
    setScenario('normal')
  }

  function newConversation() {
    const id = nextConversationId.current++
    const time = new Date().toISOString()
    setConversations((current) => [{ id, title: '新对话', created_at: time, updated_at: time }, ...current])
    setActiveId(id)
    resetScroll()
    setSourceTarget(null)
    setNotice('')
    setSidebarOpen(false)
  }

  async function saveCard() {
    if (saving || !currentCard) return
    setSaving(true)
    setNotice('')
    try {
      const messageId = previewCardMessageIds[activeId]
      const origin = messageId ? { conversationId: activeId, messageId } : undefined
      await saveSnapshot(1, currentCard, previewDatabase, origin)
      setNotice('已收藏合成卡片。')
    } catch {
      setNotice('收藏失败，请检查浏览器存储后重试。')
    } finally {
      setSaving(false)
    }
  }

  const onFocusMessageResolved = useCallback((messageId: number, found: boolean) => {
    if (!sourceTarget || sourceTarget.conversationId !== activeId || sourceTarget.messageId !== messageId) return
    setNotice(found ? '已定位到收藏的来源消息。' : '找不到这条消息；来源会话中可能已删除或无法展示。')
  }, [activeId, sourceTarget])

  function openPreviewSource(origin: CardOrigin) {
    if (!conversations.some((item) => item.id === origin.conversationId)) {
      setSourceError('找不到收藏来源会话；它可能已删除或当前不可访问。')
      return
    }
    if (!(messages[origin.conversationId] ?? []).some((message) => message.id === origin.messageId)) {
      setSourceError('找不到这条消息；来源会话中可能已删除或无法展示。')
      return
    }

    setSourceError('')
    setNotice('正在定位收藏中的来源消息…')
    setSourceTarget(origin)
    setActiveId(origin.conversationId)
    resetScroll()
    setPanel(null)
  }

  const composer = <ChatComposer value={drafts[activeId] ?? ''} onChange={(value) => setDrafts((current) => ({ ...current, [activeId]: value }))} onSend={send} disabled={!canCompose} />

  const sidebar = <ConversationSidebar
    conversations={conversations}
    activeId={activeId}
    user={{ id: 1, username: 'preview', display_name: '预览用户' }}
    open={sidebarOpen}
    desktopCollapsed={desktopSidebarCollapsed}
    activePanel={panel}
    hideActiveConversation={isHome && conversations.find((item) => item.id === activeId)?.title === '新对话'}
    onSelect={(id) => { setSourceTarget(null); setActiveId(id); resetScroll(); setNotice(''); setSourceError(''); setSidebarOpen(false) }}
    onNew={newConversation}
    onOpenPanel={(nextPanel) => { setSourceTarget(null); setSourceError(''); setPanelOpenedByUser(true); setPanel(nextPanel); setSidebarOpen(false) }}
    onToggleDesktopSidebar={() => setDesktopSidebarCollapsed((collapsed) => !collapsed)}
    onClose={() => setSidebarOpen(false)}
    onLogout={() => setNotice('合成预览无需登录。')}
  />
  const workspace = panel && <WorkspacePanelFrame key={panel} panel={panel} focusOnMount={panelOpenedByUser} onClose={() => setPanel(null)} hidden={hidden} onTogglePrivacy={() => setHidden((value) => !value)}>
    {panel === 'assets' && scenario === 'error' && <p role="alert" className="text-sm text-muted">样例：资产加载失败，请重试。</p>}
    {panel === 'assets' && scenario === 'loading' && <p role="status" className="text-sm text-muted">样例：正在加载资产…</p>}
    {panel === 'assets' && (scenario === 'empty' || scenario === 'normal') && <PreviewAssets key={activeId} hidden={hidden} onIntent={(intent) => { setIntents((current) => ({ ...current, [activeId]: intent })); setNotice(''); setPanel(null) }} />}
    {panel === 'collections' && <><p className="mb-5 text-xs text-muted">合成预览使用独立收藏空间。</p>{sourceError && <p role="alert" className="mb-4 text-sm text-red-700">{sourceError}</p>}<CollectionPanel userId={1} hidden={hidden} databaseName={previewDatabase} onOpenSource={openPreviewSource} /></>}
    {panel === 'activity' && <ActivityList entries={previewActivity} />}
  </WorkspacePanelFrame>
  return <BankWorkspace sidebarCollapsed={desktopSidebarCollapsed} sidebar={sidebar} panel={workspace} overlay={previewAction && <PendingActionDialog event={previewAction.event} transport={previewAction.transport} hidden={hidden} onTogglePrivacy={() => setHidden((value) => !value)} supplementalDescription="合成预览，操作及金额仅为样例。" verificationHint="样例中输入任意数字即可。" onClose={() => setPreviewAction(null)} />}>
    <WorkspaceHeader
      title={conversations.find((item) => item.id === activeId)?.title ?? '新对话'}
      isHome={isHome}
      sidebarOpen={sidebarOpen}
      onOpenSidebar={() => setSidebarOpen(true)}
      status={<PreviewStatus scenario={scenario} onChange={(nextScenario) => { setScenario(nextScenario); resetScroll() }} />}
    />
    <MobilePreviewStatus scenario={scenario} onChange={(nextScenario) => { setScenario(nextScenario); resetScroll() }} />
    <LayoutGroup id="bank-agent-product-preview">
    <motion.div ref={scrollRef} layoutScroll onScroll={onScroll} role={isHome ? undefined : 'log'} aria-label={isHome ? undefined : '对话消息'} aria-live="off" className="scroll-thin flex-1 overflow-y-auto">
      {scenario === 'error' ? (
        <div className="grid h-full place-items-center px-6 text-center">
          <div>
            <p role="alert" className="text-sm text-muted">样例：对话暂时无法加载。</p>
            <button type="button" onClick={() => setScenario('normal')} className="mt-4 rounded-xl border border-line bg-white px-4 py-2 text-sm text-jade-800">恢复样例</button>
          </div>
        </div>
      ) : scenario === 'loading' ? (
        <ConversationLoading label="样例：正在加载对话" />
      ) : isHome ? (
        <ChatHome
          composer={composer}
          suggestions={previewSuggestions}
          onPick={(prompt) => setDrafts((current) => ({ ...current, [activeId]: prompt }))}
          disclaimer="AI 生成内容仅供参考，重要信息请以银行正式记录为准"
        />
      ) : currentMessages.length ? (
        <MessageList
          messages={currentMessages}
          streamingText=""
          thinking={false}
          focusMessageId={sourceTarget?.conversationId === activeId ? sourceTarget.messageId : null}
          onFocusMessageResolved={onFocusMessageResolved}
          renderAfterMessage={(message) => currentCard && message.id === previewCardMessageIds[activeId] ? (
            <div className="ml-0 max-w-[560px] sm:ml-11">
              <IntelligentCard
                value={currentCard}
                hidden={hidden}
                onAction={(action) => {
                  setPanelOpenedByUser(true)
                  setPanel(action === 'open_assets' ? 'assets' : action === 'open_activity' ? 'activity' : 'collections')
                }}
              />
              <button type="button" onClick={() => void saveCard()} disabled={saving} className="mt-3 inline-flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-jade-800 hover:bg-jade-50 disabled:text-muted">
                <BookmarkPlus size={16} />{saving ? '正在收藏…' : '收藏卡片'}
              </button>
            </div>
          ) : null}
        />
      ) : null}
    </motion.div>
    {!isHome && (
      <div className="shrink-0 px-4 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-2 md:px-6">
        {scenario === 'normal' && intents[activeId] && (
          <div className="mx-auto mb-2 flex max-w-[680px] flex-wrap items-center gap-2 rounded-xl bg-jade-50 px-3 py-2 text-sm text-jade-900">
            <span className="min-w-0 flex-1 break-words">{hidden ? '意图内容已隐藏' : `转账 · ${intents[activeId].source.label} → ${intents[activeId].target.label}`}</span>
            <button type="button" onClick={() => { const intent = intents[activeId]; if (intent) setPreviewAction({ event: makePreviewAction(intent), transport: createPreviewActionTransport() }) }} className="underline">查看模拟确认</button>
            <button type="button" onClick={() => setIntents((current) => ({ ...current, [activeId]: undefined }))} className="underline">移除</button>
          </div>
        )}
        {hasNewContent && <button type="button" onClick={jumpToLatest} className="mx-auto mb-2 block rounded-full border border-line bg-white px-3 py-1 text-xs text-jade-800">查看新消息</button>}
        {notice && !panel && <p role="status" className="mx-auto mb-2 max-w-[680px] text-sm text-muted">{notice}</p>}
        {composer}
      </div>
    )}
    </LayoutGroup>
  </BankWorkspace>
}
