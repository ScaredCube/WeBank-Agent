import { useRef, useState } from 'react'
import type { PanInfo } from 'motion/react'
import { DraggableAccount } from '@/features/assets/DraggableAccount'
import { AssetEntry } from '@/features/assets/AssetEntry'
import { AssetSection } from '@/features/assets/AssetSection'
import { AssetSectionNavigation, type AssetSectionKey } from '@/features/assets/AssetSectionNavigation'
import { makeIntent, type IntentEntity, type TransferIntent } from '@/features/assets/intent'
import { previewAccounts, previewContacts, previewHoldings } from './scenarios'

export function PreviewAssets({ hidden, onIntent }: { hidden: boolean; onIntent: (intent: TransferIntent) => void }) {
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
    <AssetSection id="asset-section-accounts" title="银行账户" count={previewAccounts.length}><div className="space-y-3">{previewAccounts.map(({ entity, masked, note }, index) => <div key={entity.id}>
      <div className="relative">
      <DraggableAccount label={hidden ? `账户 ${index + 1} 已隐藏` : `${entity.label} · ${masked.slice(-4)}`} selected={source?.id === entity.id}
        onChoose={() => { setSource(entity); setNotice('已选择付款账户，请选择联系人。') }}
        onMove={(info) => setHovered(contactAt(info)?.id ?? null)}
        onDrop={(info) => { setHovered(null); const target = contactAt(info); if (target) combine(entity, target); else setNotice('未放到可用目标，已返回原位。') }}
        onCancel={() => setHovered(null)} />
      <button type="button" aria-label={hidden ? `查看账户 ${index + 1} 详情` : `查看${entity.label}详情`} aria-expanded={details === entity.id} onClick={() => setDetails(details === entity.id ? null : entity.id)} className="absolute bottom-2 right-2 z-20 min-h-9 rounded-lg px-3 text-xs text-jade-800 hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">详情</button>
      </div>
      {details === entity.id && <p className="px-2 py-2 text-xs text-muted">{hidden ? '内容已隐藏' : note}</p>}
    </div>)}</div></AssetSection>
    <AssetSection id="asset-section-contacts" title="联系人" count={previewContacts.length}><div className="space-y-3">{previewContacts.map(({ entity, detail }, index) => <div key={entity.id}>
      <div className="relative">
      <button ref={(element) => { if (element) contactRefs.current.set(entity.id, element); else contactRefs.current.delete(entity.id) }} type="button" onClick={() => { if (!source) { setNotice('请先选择付款账户。'); return } combine(source, entity) }} className={`w-full rounded-2xl border px-4 py-4 text-left text-sm ${hovered === entity.id || source ? 'border-jade-600 bg-jade-50' : 'border-line bg-white'}`}>
        {hidden ? `联系人 ${index + 1} 已隐藏` : entity.label}{source && <span className="mt-1 block text-xs text-muted">选择收款联系人</span>}
      </button>
      <button type="button" aria-label={hidden ? `查看联系人 ${index + 1} 详情` : `查看${entity.label}详情`} aria-expanded={details === entity.id} onClick={() => setDetails(details === entity.id ? null : entity.id)} className="absolute right-2 top-1/2 min-h-9 -translate-y-1/2 rounded-lg px-3 text-xs text-jade-800 hover:bg-jade-100 focus-visible:outline-2 focus-visible:outline-jade-700">详情</button>
      </div>
      {details === entity.id && <p className="px-2 py-2 text-xs text-muted">{hidden ? '内容已隐藏' : detail}</p>}
    </div>)}</div>{notice && <p role="status" className="mt-2 text-sm text-muted">{notice}</p>}</AssetSection>
    <AssetSection id="asset-section-holdings" title="理财持仓" count={previewHoldings.length}><div className="space-y-3">{previewHoldings.map((item, index) => <AssetEntry key={item.name} title={item.name} detail={item.detail} hidden={hidden} hiddenLabel={`持仓 ${index + 1} 已隐藏`}><p className="text-sm text-muted">{hidden ? '内容已隐藏' : item.note}</p></AssetEntry>)}</div></AssetSection>
  </div>
}
