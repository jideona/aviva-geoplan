import { useEffect, useState } from 'react'
import { api, type Clearance, type NamingQueue } from '../api/client'

/**
 * Serves two workflows deliberately: desk entry against a reference now, and
 * field capture later. The difference is the source recorded, which determines
 * whether the name may ever be redistributed.
 */
// Consumer-map sourcing is deliberately absent. Streets carry their
// provisional code until a surveyor supplies a name from a source Aviva owns,
// which avoids the licence problem rather than deferring it.
const SOURCES = [
  { value: 'field_photo', label: 'Field — sign photographed', clean: true },
  { value: 'field_observed', label: 'Field — observed', clean: true },
  { value: 'authority', label: 'Authority register (AGIS/FCDA)', clean: true },
  { value: 'operator_knowledge', label: 'Local knowledge (confirm in field)', clean: true },
]

export default function NamingPanel(
  { projectId, onNamed }: { projectId: string; onNamed: () => void },
) {
  const [queue, setQueue] = useState<NamingQueue | null>(null)
  const [clearance, setClearance] = useState<Clearance | null>(null)
  const [source, setSource] = useState('field_photo')
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = () => {
    api.namingQueue(projectId).then(setQueue).catch(() => {})
    api.clearance(projectId).then(setClearance).catch(() => {})
  }
  useEffect(reload, [projectId])

  async function save(streetId: string) {
    const name = (drafts[streetId] ?? '').trim()
    if (name.length < 2) return
    setSaving(streetId); setError(null)
    try {
      await api.nameStreet(projectId, streetId, { name, source })
      setDrafts((d) => { const n = { ...d }; delete n[streetId]; return n })
      reload(); onNamed()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the name.')
    } finally { setSaving(null) }
  }

  const chosen = SOURCES.find((s) => s.value === source)

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Street naming</h2>

      <label className="label" htmlFor="src">Source for these names</label>
      <select id="src" className="field" value={source}
              onChange={(e) => setSource(e.target.value)}>
        {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
      </select>

      {chosen && !chosen.clean && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-xs text-navy">
          Names entered under this source are tagged and excluded from
          commercial delivery.
        </p>
      )}
      <p className="mt-2 text-xs text-steel">
        Unnamed streets keep their provisional code until a surveyor supplies a
        name. The code is stable, so nothing downstream breaks while the name is
        outstanding.
      </p>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-xs">
          {error}
        </p>
      )}

      {queue && (
        <>
          <p className="mt-3 text-xs text-steel">
            {queue.unnamed_streets} unnamed roads carrying{' '}
            {queue.buildings_affected.toLocaleString()} buildings. Highest
            impact first.
          </p>
          <div className="mt-2 max-h-96 space-y-2 overflow-auto">
            {queue.streets.filter((s) => !s.name).slice(0, 60).map((s) => (
              <div key={s.id} className="card p-2">
                <div className="flex items-baseline justify-between">
                  <span className="font-mono text-[10px] text-brand">{s.street_code}</span>
                  <span className="font-mono text-[10px] text-steel">
                    {s.road_class} · {(s.length_m / 1000).toFixed(2)} km ·{' '}
                    <b className="text-navy">{s.building_count}</b> bldg
                  </span>
                </div>
                <div className="mt-1 flex gap-1">
                  <input
                    className="field py-1 text-xs" placeholder="Street name"
                    value={drafts[s.id] ?? ''}
                    onChange={(e) => setDrafts({ ...drafts, [s.id]: e.target.value })}
                    onKeyDown={(e) => { if (e.key === 'Enter') void save(s.id) }}
                  />
                  <button className="btn-primary px-3 py-1 text-xs"
                          disabled={saving === s.id || (drafts[s.id] ?? '').trim().length < 2}
                          onClick={() => void save(s.id)}>
                    {saving === s.id ? '…' : 'Save'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {clearance && (
        <div className={`mt-3 rounded border-l-2 p-3 text-xs ${
          clearance.clear_for_commercial_delivery
            ? 'border-teal bg-lightgrey' : 'border-brand bg-lightgrey'}`}>
          <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
            Commercial clearance
          </p>
          <p className="mt-1 text-navy">{clearance.note}</p>
          {clearance.streets_requiring_re_sourcing > 0 && (
            <p className="mt-1 text-steel">{clearance.remedy}</p>
          )}
          {Object.keys(clearance.name_sources).length > 0 && (
            <div className="mt-2 border-t border-pale pt-2">
              {Object.entries(clearance.name_sources).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-steel">{k.replace(/_/g, ' ')}</span>
                  <span className="font-mono text-navy">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
