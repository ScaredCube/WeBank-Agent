export type AssetSectionKey = 'accounts' | 'cards' | 'contacts' | 'holdings' | 'bill'
const sections: { id: AssetSectionKey; label: string }[] = [
  { id: 'accounts', label: '账户' }, { id: 'cards', label: '银行卡' },
  { id: 'contacts', label: '联系人' }, { id: 'holdings', label: '持仓' },
  { id: 'bill', label: '账单' },
]

export function AssetSectionNavigation({ active, onSelect }: {
  active: AssetSectionKey
  onSelect: (section: AssetSectionKey) => void
}) {
  return <nav aria-label="资产分类" role="tablist" className="sticky top-0 z-20 -mx-5 mb-7 border-b border-line bg-workspace px-5 pb-3 pt-2 sm:-mx-7 sm:px-7">
    <div className="grid grid-cols-5 gap-1 rounded-2xl border border-line bg-panel p-1 shadow-[0_5px_18px_-14px_rgba(0,40,30,.3)]">
      {sections.map((section) => <button
        key={section.id} type="button" role="tab"
        id={`asset-tab-${section.id}`}
        aria-controls={`asset-panel-${section.id}`}
        aria-selected={active === section.id}
        onClick={() => onSelect(section.id)}
        className={`relative min-h-11 rounded-xl px-1 text-[12px] transition-colors sm:text-[13px] focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-jade-700 ${active === section.id
          ? 'bg-jade-50 font-semibold text-jade-900' : 'text-muted hover:bg-jade-50/50 hover:text-ink'}`}>
        {section.label}
        {active === section.id && <span aria-hidden="true" className="absolute inset-x-1/4 bottom-1 h-0.5 rounded-full bg-jade-700" />}
      </button>)}
    </div>
  </nav>
}
