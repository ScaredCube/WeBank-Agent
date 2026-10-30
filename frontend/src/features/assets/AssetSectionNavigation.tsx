export type AssetSectionKey = 'accounts' | 'cards' | 'contacts' | 'holdings' | 'bill'

const sections: Array<{ id: AssetSectionKey; label: string }> = [
  { id: 'accounts', label: '账户' },
  { id: 'cards', label: '银行卡' },
  { id: 'contacts', label: '联系人' },
  { id: 'holdings', label: '持仓' },
  { id: 'bill', label: '账单' },
]

export function AssetSectionNavigation({ active, onSelect }: {
  active: AssetSectionKey
  onSelect: (section: AssetSectionKey) => void
}) {
  function navigateTo(section: AssetSectionKey) {
    onSelect(section)
    const target = document.getElementById(`asset-section-${section}`)
    if (!target) return
    const reducedMotion = typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reducedMotion ? 'instant' : 'smooth', block: 'start' })
  }

  return (
    <nav aria-label="资产分类" className="sticky top-0 z-10 -mx-5 mb-7 grid grid-cols-5 rounded-xl border border-line bg-panel p-1">
      {sections.map((section) => (
        <button
          key={section.id}
          type="button"
          aria-current={active === section.id ? 'location' : undefined}
          onClick={() => navigateTo(section.id)}
          className={`relative min-h-10 rounded-lg px-2 text-[13px] transition-colors focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-jade-700 ${
            active === section.id
              ? 'bg-white font-semibold text-ink shadow-[0_1px_3px_rgba(18,39,31,0.08)]'
              : 'text-muted hover:bg-white/70 hover:text-ink'
          }`}
        >
          {section.label}
          {active === section.id && <span aria-hidden="true" className="absolute inset-x-5 bottom-0 h-0.5 rounded-full bg-jade-700" />}
        </button>
      ))}
    </nav>
  )
}
