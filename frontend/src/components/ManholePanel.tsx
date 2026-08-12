import { useEffect, useMemo, useState } from 'react'
import { api } from '../api/client'
import MediaGallery from './MediaGallery'

interface ManholeRow {
  id: string; code: string | null; type: string; condition: string
  notes: string | null; surveyed_by: string | null; assessed_at: string | null
}

const CONDITION_COLOR: Record<string, string> = {
  good: '#00C9A7', fair: '#4BAADF', poor: '#B45309', damaged: '#E5484D',
  buried: '#8FA3BF', inaccessible: '#E5484D', unknown: '#5A739A',
}

interface Props { projectId: string }

/**
 * Field-surveyed chambers, reviewed as a list rather than picked off the map —
 * useful when checking survey completeness/condition rather than a specific
 * location. Reuses the same manholes.geojson the map layer draws from, so
 * there's one source of truth and no new backend endpoint.
 */
export default function ManholePanel({ projectId }: Props) {
  const [rows, setRows] = useState<ManholeRow[] | null>(null)
  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.manholesGeoJSON(projectId).then((fc) => {
      setRows(fc.features.map((f) => ({
        id: String(f.properties?.id ?? ''),
        code: f.properties?.code ?? null,
        type: String(f.properties?.type ?? 'manhole'),
        condition: String(f.properties?.condition ?? 'unknown'),
        notes: f.properties?.notes ?? null,
        surveyed_by: f.properties?.surveyed_by ?? null,
        assessed_at: f.properties?.assessed_at ?? null,
      })))
    }).catch((e) => setError(e instanceof Error ? e.message : 'Could not load manholes.'))
  }, [projectId])

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!rows) return []
    return rows.filter((r) => !q
      || (r.code ?? '').toLowerCase().includes(q)
      || r.type.toLowerCase().includes(q))
  }, [rows, query])

  if (rows === null) {
    return (
      <div className="mt-6 border-t border-lightgrey pt-4">
        <h2 className="label">Manholes / chambers</h2>
        {error
          ? <p className="text-xs text-steel">{error}</p>
          : <p className="text-xs text-steel">Loading…</p>}
      </div>
    )
  }

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Manholes / chambers ({rows.length})</h2>
      {rows.length === 0 ? (
        <p className="text-xs text-steel">
          None captured yet — chambers are added from the mobile survey app.
        </p>
      ) : (
        <>
          <input className="field mt-1" placeholder="Search code or type"
                 value={query} onChange={(e) => setQuery(e.target.value)} />
          <div className="mt-1 max-h-80 space-y-1 overflow-auto">
            {visible.map((r) => {
              const open = openId === r.id
              return (
                <div key={r.id}
                     className={`rounded border px-2 py-1.5 ${
                       open ? 'border-brand bg-lightgrey' : 'border-transparent hover:bg-lightgrey'}`}>
                  <button className="w-full text-left"
                          onClick={() => setOpenId(open ? null : r.id)}>
                    <div className="flex items-baseline justify-between">
                      <span className="text-xs text-navy">{r.code ?? 'uncoded'}</span>
                      <span className="font-mono text-[9px] uppercase text-steel">{r.type}</span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-1">
                      <span className="inline-block h-2 w-2 rounded-sm"
                            style={{ background: CONDITION_COLOR[r.condition] ?? '#5A739A' }} />
                      <span className="text-[10px] text-steel">{r.condition}</span>
                      {r.surveyed_by && (
                        <span className="text-[10px] text-midgrey"> · {r.surveyed_by}</span>
                      )}
                    </div>
                  </button>
                  {open && (
                    <div className="mt-2 border-t border-pale pt-2">
                      {r.notes && <p className="text-[11px] text-navy">{r.notes}</p>}
                      <MediaGallery projectId={projectId} entityType="manhole"
                                    entityId={r.id} hideWhenEmpty={false} />
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
