import { useMemo, useState } from 'react'
import { api, type ParcelListing, type ParcelRow } from '../api/client'

type Filter = 'needs_name' | 'named' | 'all'

interface Props {
  projectId: string
  listing: ParcelListing | null
  selectedId: string | null
  onSelect: (id: string | null) => void
  onChanged: () => void
}

export default function ParcelNamingPanel(
  { projectId, listing, selectedId, onSelect, onChanged }: Props,
) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('needs_name')
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const rows = listing?.parcels ?? []
  const counts = useMemo(() => ({
    needs_name: rows.filter((p) => p.needs_name).length,
    named: rows.filter((p) => !p.needs_name).length,
    all: rows.length,
  }), [rows])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return rows
      .filter((p) => filter === 'all'
        || (filter === 'needs_name' ? p.needs_name : !p.needs_name))
      .filter((p) => !q
        || p.parcel_code.toLowerCase().includes(q)
        || p.name.toLowerCase().includes(q)
        || (p.survey_code ?? '').toLowerCase().includes(q))
  }, [rows, filter, query])

  async function save(parcel: ParcelRow) {
    const name = draft.trim()
    if (name.length < 2) return
    setSaving(true); setError(null)
    try {
      await api.renameParcel(projectId, parcel.id, name)
      setDraft(''); onSelect(null); onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save the name.')
    } finally { setSaving(false) }
  }

  if (!listing) return null

  return (
    <div className="mt-4 border-t border-lightgrey pt-3">
      <h3 className="label">Estate names</h3>

      <input className="field" placeholder="Search name, code or GC number"
             value={query} onChange={(e) => setQuery(e.target.value)} />

      <div className="mt-2 flex gap-1">
        {(['needs_name', 'named', 'all'] as Filter[]).map((f) => (
          <button key={f}
                  className={`flex-1 rounded px-1.5 py-1 font-mono text-[10px] uppercase
                    ${filter === f ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
                  onClick={() => setFilter(f)}>
            {f === 'needs_name' ? 'unnamed' : f} {counts[f]}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}

      <div className="mt-2 max-h-80 space-y-1 overflow-auto">
        {visible.map((p) => {
          const open = selectedId === p.id
          return (
            <div key={p.id}
                 className={`rounded border px-2 py-1.5 ${
                   open ? 'border-brand bg-lightgrey'
                        : 'border-transparent hover:bg-lightgrey'}`}>
              <button className="w-full text-left"
                      onClick={() => {
                        onSelect(open ? null : p.id)
                        setDraft(p.needs_name ? '' : p.name)
                      }}>
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-[10px] text-brand">
                    {p.survey_code ?? p.parcel_code}
                  </span>
                  <span className="font-mono text-[10px] text-steel">
                    {(p.area_sqm / 1000).toFixed(1)}k m² · {p.buildings} bldg
                    {p.units ? ` · ${p.units}u` : ''}
                  </span>
                </div>
                <span className={p.needs_name ? 'text-xs text-midgrey' : 'text-xs text-navy'}>
                  {p.needs_name ? 'needs a name' : p.name}
                </span>
              </button>

              {open && (
                <div className="mt-2 border-t border-pale pt-2">
                  {p.raw_name && p.raw_name !== p.name && (
                    <p className="mb-1 truncate font-mono text-[9px] text-steel">
                      as surveyed: {p.raw_name}
                    </p>
                  )}
                  <div className="flex gap-1">
                    <input autoFocus className="field py-1 text-xs"
                           placeholder="Estate name" value={draft}
                           onChange={(e) => setDraft(e.target.value)}
                           onKeyDown={(e) => { if (e.key === 'Enter') void save(p) }} />
                    <button className="btn-primary px-3 py-1 text-xs"
                            disabled={saving || draft.trim().length < 2}
                            onClick={() => void save(p)}>
                      {saving ? '…' : 'Save'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )
        })}
        {visible.length === 0 && (
          <p className="px-2 py-4 text-center text-xs text-steel">
            Nothing matches that search.
          </p>
        )}
      </div>
    </div>
  )
}
