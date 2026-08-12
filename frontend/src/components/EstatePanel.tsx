import { useEffect, useState } from 'react'
import { api, type EstateWorklist } from '../api/client'

/**
 * Naming an estate's access way after the estate is what makes its observed
 * unit counts locatable. This ranks the remaining estates by how many units
 * each one unlocks, so the naming effort goes where the data is.
 */
export default function EstatePanel({ projectId }: { projectId: string }) {
  const [data, setData] = useState<EstateWorklist | null>(null)
  const [showLocated, setShowLocated] = useState(false)

  useEffect(() => {
    api.estates(projectId).then(setData).catch(() => {})
  }, [projectId])

  if (!data) return null
  if (!data.available) {
    return (
      <div className="mt-6 border-t border-lightgrey pt-4">
        <h2 className="label">Estate data</h2>
        <p className="text-xs text-steel">{data.reason}</p>
      </div>
    )
  }

  const total = (data.units_located ?? 0) + (data.units_pending ?? 0)
  const pct = total ? Math.round((data.units_located ?? 0) / total * 100) : 0

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Estate data</h2>

      <div className="flex justify-between text-xs">
        <span className="text-steel">Observed units locatable</span>
        <span className="font-mono text-navy">
          {(data.units_located ?? 0).toLocaleString()} / {total.toLocaleString()} ({pct}%)
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-lightgrey">
        <div className="h-full bg-teal" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 font-mono text-[10px] text-steel">
        {data.located} of {data.estates_total} estates · {data.buildings_located} buildings
      </p>

      {(data.worklist?.length ?? 0) > 0 && (
        <>
          <p className="mt-3 rounded border-l-2 border-teal bg-lightgrey px-2 py-1.5 text-[11px] text-navy">
            Name the access way serving each estate below — using the estate
            name — and its unit counts become locatable.
          </p>
          <div className="mt-2 max-h-72 space-y-0.5 overflow-auto">
            {data.worklist!.map((e) => (
              <div key={e.estate}
                   className="flex items-baseline justify-between px-2 py-1 text-xs">
                <span className="truncate pr-2 text-navy">{e.estate}</span>
                <span className="shrink-0 font-mono text-[10px] text-steel">
                  {e.buildings} bldg · <b className="text-navy">{e.units}</b> units
                </span>
              </div>
            ))}
          </div>
        </>
      )}

      <button className="btn-ghost mt-2 w-full py-1 text-[11px]"
              onClick={() => setShowLocated(!showLocated)}>
        {showLocated ? 'Hide' : 'Show'} {data.located} located estates
      </button>

      {showLocated && (
        <div className="mt-1 max-h-56 space-y-0.5 overflow-auto">
          {data.located_estates!.map((e) => (
            <div key={e.estate} className="px-2 py-1 text-[11px]">
              <div className="flex justify-between">
                <span className="truncate pr-2 text-navy">{e.estate}</span>
                <span className="font-mono text-[10px] text-teal">
                  {e.units} units
                </span>
              </div>
              <p className="font-mono text-[9px] text-steel">
                → {e.street_name} ({Math.round(e.match_score * 100)}%)
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
