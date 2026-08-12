import type { ReactNode } from 'react'

interface Props {
  tabs: { value: string; label: string }[]
  active: string
  onChange: (v: string) => void
  children: ReactNode
}

/** Compact segmented tab row, used inside the Design accordion section to
 * switch between Layer / Edit / Review without floating separate panels
 * over the map. */
export default function Tabs({ tabs, active, onChange, children }: Props) {
  return (
    <div>
      <div className="mb-2 flex gap-1">
        {tabs.map((t) => (
          <button key={t.value}
            className={`flex-1 rounded px-2 py-1 text-[11px] ${
              active === t.value ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
            onClick={() => onChange(t.value)}>
            {t.label}
          </button>
        ))}
      </div>
      {children}
    </div>
  )
}
