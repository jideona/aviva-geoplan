import { useEffect, useState } from 'react'
import { api, type AssignmentResult, type NamingQueue } from '../api/client'

export default function AssignmentPanel(
  { projectId, onDone }: { projectId: string; onDone: () => void },
) {
  const [maxDistance, setMaxDistance] = useState(60)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AssignmentResult | null>(null)
  const [queue, setQueue] = useState<NamingQueue | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadQueue = () => api.namingQueue(projectId).then(setQueue).catch(() => {})
  useEffect(() => { void loadQueue() }, [projectId])

  async function run() {
    setBusy(true); setError(null)
    try {
      setResult(await api.runAssignment(projectId, maxDistance))
      await loadQueue()
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Assignment failed.')
    } finally { setBusy(false) }
  }

  const pct = result && result.total
    ? Math.round((result.assigned / result.total) * 100) : 0

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Street assignment</h2>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="label" htmlFor="maxd">Max distance (m)</label>
          <input id="maxd" type="number" min={10} max={500} className="field"
                 value={maxDistance}
                 onChange={(e) => setMaxDistance(Number(e.target.value))} />
        </div>
        <button className="btn-primary" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run'}
        </button>
      </div>

      {error && (
        <p className="mt-3 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm">
          {error}
        </p>
      )}

      {result && (
        <div className="card mt-3 p-3 text-xs">
          <div className="mb-2 flex justify-between">
            <span className="text-steel">Assigned</span>
            <span className="font-mono text-navy">
              {result.assigned.toLocaleString()} / {result.total.toLocaleString()} ({pct}%)
            </span>
          </div>
          <div className="mb-2 h-1.5 overflow-hidden rounded bg-lightgrey">
            <div className="h-full bg-brand" style={{ width: `${pct}%` }} />
          </div>
          <Line label="High confidence" value={result.high_confidence} />
          <Line label="Needs review" value={result.needs_review} />
          <Line label="Low confidence" value={result.low_confidence} />
          <Line label="Unassigned" value={result.unassigned} />
          {result.skipped_protected ? (
            <Line label="Protected — field verified" value={result.skipped_protected} />
          ) : null}
          <div className="mt-2 border-t border-lightgrey pt-2">
            <Line label="On an unnamed road" value={result.needs_field_name} strong />
          </div>
        </div>
      )}

      {queue && queue.unnamed_streets > 0 && (
        <div className="mt-3 rounded border-l-2 border-teal bg-lightgrey p-3 text-xs">
          <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
            Field naming worklist
          </p>
          <p className="mt-1 text-navy">
            {queue.unnamed_streets} unnamed roads carry{' '}
            {queue.buildings_affected.toLocaleString()} buildings.
          </p>
          <p className="mt-1 text-steel">
            The geometry is assigned; only the names are missing. Naming these
            in the field converts a geometric assignment into a usable address.
          </p>
          <div className="mt-2 max-h-40 overflow-auto">
            {queue.streets.slice(0, 15).map((s) => (
              <div key={s.id} className="flex justify-between py-0.5">
                <span className="font-mono text-[10px] text-brand">{s.street_code}</span>
                <span className="text-steel">
                  {s.road_class} · {(s.length_m / 1000).toFixed(2)} km ·{' '}
                  <b className="text-navy">{s.building_count}</b>
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Line({ label, value, strong }: { label: string; value: number; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-steel">{label}</span>
      <span className={strong ? 'font-mono text-navy' : 'font-mono text-steel'}>
        {value.toLocaleString()}
      </span>
    </div>
  )
}
