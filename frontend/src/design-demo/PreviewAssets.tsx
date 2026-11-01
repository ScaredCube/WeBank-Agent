import { useRef, useState } from 'react'
import type { PanInfo } from 'motion/react'
import { DraggableAccount } from '@/features/assets/DraggableAccount'
import { AssetEntry } from '@/features/assets/AssetEntry'
import { AssetSection } from '@/features/assets/AssetSection'
import { AssetSectionNavigation, type AssetSectionKey } from '@/features/assets/AssetSectionNavigation'
import { makeIntent, type IntentEntity, type TransferIntent } from '@/features/assets/intent'
import { previewAccounts, previewContacts, previewHoldings } from './scenarios'
import { ReferenceSource } from '@/features/references/ReferenceSource'
import type { BankObjectReference } from '@/features/references/bank-object-reference'

export function PreviewAssets({ hidden, onIntent, onReference }: { hidden: boolean; onIntent: (intent: TransferIntent) => void; onReference?: (reference: BankObjectReference) => void }) {
  const [source, setSource] = useState<IntentEntity | null>(null)
  const [hovered, setHovered] = useState<string | null>(null)
  const [details, setDetails] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [activeSection, setActiveSection] = useState<AssetSectionKey>('accounts')
  const contactRefs = useRef(new Map<string, HTMLButtonElement>())

  function contactAt(info: PanInfo): IntentEntity | null {
    for (const contact of previewContacts) {
      const rect = contactRefs.current.get(contact.entity.id)?.getBoundingClientRect()
      if (rect && info.point.x >= rect.left + window.scrollX && info.point.x <= rect.right + window.scrollX && info.point.y >= rect.top + window.scrollY && info.point.y <= rect.bottom + window.scrollY) return contact.entity
    }
    return null
  }
  function combine(account: IntentEntity, contact: IntentEntity) {
    const intent = makeIntent(account, contact)
    if (!intent) { setNotice('所选对象不能组合。'); return }
    onIntent(intent)
  }

  return <div className="space-y-7">
    <AssetSectionNavigation active={activeSection} onSelect={setActiveSection} />
    {activeSection === 'accounts' && <AssetSection id="asset-section-accounts" title="银行账户" count={previewAccounts.length}><div className="space-y-3">{previewAccounts.map(({ entity, masked }, index) => <div key={entity.id}>
      <ReferenceSource reference={{kind:"account",id:index+1,label:hidden ? `账户 ${index+1}` : entity.label,detail:hidden ? "" : masked}} onReference={onReference}>
      <div className="relative">
      <DraggableAccount label={hidden ? `账户 ${index + 1} 已隐藏` : `${entity.label} · ${masked.slice(-4)}`} selected={source?.id === entity.id}
        onChoose={() => { setSource(entity); setNotice('已选择付款账户，请选择联系人。') }}
        onMove={(info) => setHovered(contactAt(info)?.id ?? null)}
        onDrop={(info) => { setHovered(null); const target = contactAt(info); if (target) combine(entity, target); else setNotice('未放到可用目标，已返回原位。') }}
        onCancel={() => setHovered(null)} />
      <button type="button" aria-label={hidden ? `查看账户 ${index + 1} 详情` : `查看${entity.label}详情`} aria-expanded={details === entity.id} onClick={() => setDetails(details === entity.id ? null : entity.id)} className="absolute bottom-2 left-2 z-20 min-h-9 rounded-lg bg-panel px-3 text-xs text-jade-800 hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">详情</button>
      </div>
      {details === entity.id && <div className="mt-2 rounded-xl bg-panel p-4 text-sm text-ink"><span className="text-muted">账户</span><span className="ml-3">{hidden ? '内容已隐藏' : `${entity.label} · ${masked}`}</span></div>}
    </ReferenceSource>
    </div>)}</div></AssetSection>}
    {activeSection === 'cards' && <AssetSection id="asset-section-cards" title="银行卡" count={2}>
      <div className="grid gap-3">
        {previewAccounts.map(({entity,masked},index) => <ReferenceSource key={entity.id} reference={{kind:'card',id:index+11,label:hidden ? `银行卡 ${index+1}` : entity.label+'卡',detail:hidden ? '' : masked}} onReference={onReference}>
          <div className="relative overflow-hidden rounded-[18px] border border-jade-200 bg-gradient-to-br from-[#17463b] via-[#246556] to-[#163d35] p-5 text-white shadow-[0_16px_32px_-25px_rgba(4,35,26,.7)]">
            <div className="flex items-start justify-between text-xs font-medium"><span>WeBank · 模拟银行卡</span><span className="rounded-md border border-white/20 px-2 py-1 text-[10px]">借记卡</span></div>
            <div aria-hidden="true" className="mt-7 h-3 w-5 rounded-[4px] bg-amber-200/80"/>
            <p className="mt-4 font-mono text-[18px] tracking-[0.15em]">{hidden ? '•••• ••••' : masked}</p>
            <p className="mt-2 text-[11px] text-white/75">{hidden ? `银行卡 ${index+1}` : entity.label} · 演示卡面</p>
          </div>
        </ReferenceSource>)}
      </div>
    </AssetSection>}
    {activeSection === 'contacts' && <AssetSection id="asset-section-contacts" title="联系人" count={previewContacts.length}><div className="space-y-3">{previewContacts.map(({ entity, detail }, index) => <div key={entity.id}>
      <ReferenceSource reference={{kind:"contact",id:index+1,label:hidden ? `联系人 ${index+1}` : entity.label,detail:hidden ? "" : detail}} onReference={onReference}>
      <div className="relative">
      <button ref={(element) => { if (element) contactRefs.current.set(entity.id, element); else contactRefs.current.delete(entity.id) }} type="button" onClick={() => { if (!source) { setNotice('请先选择付款账户。'); return } combine(source, entity) }} className={`w-full rounded-2xl border px-4 py-4 text-left text-sm ${hovered === entity.id || source ? 'border-jade-600 bg-jade-50' : 'border-line bg-white'}`}>
        {hidden ? `联系人 ${index + 1} 已隐藏` : entity.label}{source && <span className="mt-1 block text-xs text-muted">选择收款联系人</span>}
      </button>
      <button type="button" aria-label={hidden ? `查看联系人 ${index + 1} 详情` : `查看${entity.label}详情`} aria-expanded={details === entity.id} onClick={() => setDetails(details === entity.id ? null : entity.id)} className="absolute right-2 top-1/2 min-h-9 -translate-y-1/2 rounded-lg px-3 text-xs text-jade-800 hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">详情</button>
      </div>
      {details === entity.id && <p className="px-2 py-2 text-xs text-muted">{hidden ? '内容已隐藏' : detail}</p>}
    </ReferenceSource>
    </div>)}</div>{notice && <p role="status" className="mt-2 text-sm text-muted">{notice}</p>}</AssetSection>}
    {activeSection === 'holdings' && <AssetSection id="asset-section-holdings" title="理财持仓" count={previewHoldings.length}><div className="space-y-3">{previewHoldings.map((item, index) => <AssetEntry key={item.name} title={item.name} detail={item.detail} hidden={hidden} hiddenLabel={`持仓 ${index + 1} 已隐藏`}><p className="text-sm text-muted">{hidden ? '内容已隐藏' : item.note}</p></AssetEntry>)}</div></AssetSection>}
    {activeSection === 'bill' && <AssetSection id="asset-section-bill" title="账单"><div className="rounded-2xl border border-line bg-panel px-5 py-7 text-sm text-muted">从对话中查询账单，查看可信的收支结果。</div></AssetSection>}
  </div>
}
