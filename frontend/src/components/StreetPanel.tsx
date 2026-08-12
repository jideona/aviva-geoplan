import { useMemo, useState } from 'react'
import { api, type Street } from '../api/client'
import MediaGallery from './MediaGallery'

const SOURCES = [
  { value: 'field_observed', label: 'Field — observed' },
  { value: 'field_photo', label: 'Field — sign photographed' },
  { value: 'authority', label: 'Authority register' },
  { value: 'operator_knowledge', label: 'Local knowledge' },
]

type Filter = 'all' | 'unnamed' | 'identified' | 'confirmed'

interface Props {
  projectId: string
  streets: Street[]
  selectedId: string | null
  onSelect: (id: string | null) => void
  onChanged: () => void
}

export default function StreetPanel(
  { projectId, streets, selectedId, onSelect, onChanged }: Props,
) {
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('unnamed')
  const [source, setSource] = useState('field_observed')
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [merging, setMerging] = useState(false)
  const [mergeNote, setMergeNote] = useState<string | null>(null)
  const [showRemove, setShowRemove] = useState(false)
  const [removeCodes, setRemoveCodes] = useState('')
  const [removing, setRemoving] = useState(false)
  const [removeNote, setRemoveNote] = useState<string | null>(null)

  async function removeByCodes() {
    const codes = removeCodes.split(/[,\s]+/).map((c) => c.trim()).filter(Boolean)
    if (!codes.length) return
    if (!confirm(`Delete ${codes.length} street(s)? This cannot be undone.`)) return
    setRemoving(true); setError(null); setRemoveNote(null)
    try {
      const r = await api.deleteStreetsByCode(projectId, codes)
      setRemoveNote(`Deleted ${r.deleted}.` +
        (r.not_found.length ? ` Not found: ${r.not_found.join(', ')}` : ''))
      setRemoveCodes(''); onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed.')
    } finally { setRemoving(false) }
  }

  async function removeOne(street: Street) {
    if (!confirm(`Delete ${street.street_code}? This cannot be undone.`)) return
    setError(null)
    try { await api.deleteStreet(projectId, street.id); onSelect(null); onChanged() }
    catch (e) { setError(e instanceof Error ? e.message : 'Delete failed.') }
  }

  const counts = useMemo(() => ({
    all: streets.length,
    unnamed: streets.filter((s) => s.name_state === 'unnamed').length,
    identified: streets.filter((s) => s.name_state === 'identified').length,
    confirmed: streets.filter((s) => s.name_state === 'confirmed').length,
  }), [streets])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    return streets
      .filter((s) => filter === 'all' || s.name_state === filter)
      // Search both the code and the name, so "129", "WUY-ST-129" and
      // "ameh" all find their street.
      .filter((s) => !q
        || s.street_code.toLowerCase().includes(q)
        || (s.name ?? '').toLowerCase().includes(q))
      .sort((a, b) => b.length_m - a.length_m)
  }, [streets, filter, query])

  async function save(street: Street) {
    const name = draft.trim()
    if (name.length < 2) return
    setSaving(true); setError(null)
    try {
      await api.nameStreet(projectId, street.id, { name, source })
      setDraft(''); onSelect(null); onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the name.')
    } finally { setSaving(false) }
  }

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Street register</h2>

      <input
        className="field" placeholder="Search code or name — e.g. 129 or Ameh"
        value={query} onChange={(e) => setQuery(e.target.value)}
      />

      <div className="mt-2 flex gap-1">
        {(['unnamed', 'identified', 'confirmed', 'all'] as Filter[]).map((f) => (
          <button key={f}
                  className={`flex-1 rounded px-1.5 py-1 font-mono text-[10px] uppercase
                    ${filter === f ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
                  onClick={() => setFilter(f)}>
            {f === 'all' ? 'all' : f.slice(0, 5)} {counts[f]}
          </button>
        ))}
      </div>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}

      <p className="mt-2 text-[11px] text-steel">
        {visible.length} shown. Click a street here or on the map to rename it.
      </p>

      <button className="btn-ghost mt-2 w-full py-1 text-[11px]"
              disabled={merging}
              onClick={async () => {
                setMerging(true); setMergeNote(null)
                try {
                  const r = await api.consolidateStreets(projectId)
                  setMergeNote(r.note)
                  onChanged()
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Consolidation failed.')
                } finally { setMerging(false) }
              }}>
        {merging ? 'Merging…' : 'Merge segments sharing a name'}
      </button>
      <p className="mt-1 text-[10px] text-steel">
        OSM splits roads at junctions, so one street imports as several rows.
        Naming now merges automatically; run this once for names entered before.
      </p>
      {mergeNote && (
        <p className="mt-1 rounded border-l-2 border-teal bg-lightgrey px-2 py-1 text-[10px] text-navy">
          {mergeNote}
        </p>
      )}

      <button className="btn-ghost mt-2 w-full py-1 text-[11px]"
              onClick={() => setShowRemove((v) => !v)}>
        {showRemove ? 'Hide remove non-streets' : 'Remove non-streets (by code)'}
      </button>
      {showRemove && (
        <div className="mt-1 rounded border border-lightgrey p-2">
          <textarea
            className="field h-16 text-[11px]" placeholder="Paste codes, e.g. WUY-ST-216, WUY-ST-217 …"
            value={removeCodes} onChange={(e) => setRemoveCodes(e.target.value)} />
          <button className="btn-primary mt-1 w-full py-1 text-[11px] disabled:opacity-40"
                  disabled={removing || !removeCodes.trim()}
                  onClick={() => void removeByCodes()}>
            {removing ? 'Deleting…' : 'Delete these streets'}
          </button>
          <p className="mt-1 text-[10px] text-steel">
            Permanent — these lines aren't streets. Re-import OSM to restore if needed.
          </p>
          {removeNote && (
            <p className="mt-1 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-[10px] text-navy">
              {removeNote}
            </p>
          )}
        </div>
      )}

      <div className="mt-1 max-h-[28rem] space-y-1 overflow-auto">
        {visible.map((s) => {
          const open = selectedId === s.id
          return (
            <div key={s.id}
                 className={`rounded border px-2 py-1.5 ${
                   open ? 'border-brand bg-lightgrey' : 'border-transparent hover:bg-lightgrey'}`}>
              <button className="w-full text-left"
                      onClick={() => {
                        onSelect(open ? null : s.id)
                        setDraft(s.name ?? '')
                      }}>
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-[10px] text-brand">{s.street_code}</span>
                  <span className="font-mono text-[10px] text-steel">
                    {(s.length_m / 1000).toFixed(2)} km · {s.building_count}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <span className={s.name ? 'text-xs text-navy' : 'text-xs text-midgrey'}>
                    {s.name ?? 'awaiting a name'}
                  </span>
                  {s.name_state === 'confirmed' && <span className="text-teal">✓</span>}
                  {s.name_state === 'identified' && (
                    <span className="text-[9px] text-midgrey">unverified</span>
                  )}
                </div>
              </button>

              {open && (
                <div className="mt-2 border-t border-pale pt-2">
                  <input
                    autoFocus className="field py-1 text-xs"
                    placeholder="Street name"
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') void save(s) }}
                  />
                  <select className="field mt-1 py-1 text-xs" value={source}
                          onChange={(e) => setSource(e.target.value)}>
                    {SOURCES.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <div className="mt-1 flex gap-1">
                    <button className="btn-primary flex-1 py-1 text-xs"
                            disabled={saving || draft.trim().length < 2}
                            onClick={() => void save(s)}>
                      {saving ? 'Saving…' : 'Save name'}
                    </button>
                    <button className="btn-ghost py-1 text-xs"
                            onClick={() => onSelect(null)}>Cancel</button>
                    <button className="rounded px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                            title="Delete — this is not a street"
                            onClick={() => void removeOne(s)}>Delete</button>
                  </div>
                  {s.name && (
                    <p className="mt-1 text-[10px] text-steel">
                      Currently {s.name}
                      {s.name_source && ` (${s.name_source.replace(/_/g, ' ')})`}
                    </p>
                  )}
                  <MediaGallery projectId={projectId} entityType="street" entityId={s.id} />
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
