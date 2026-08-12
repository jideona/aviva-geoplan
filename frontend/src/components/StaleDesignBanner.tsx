import { useEffect, useState } from 'react'
import { api } from '../api/client'

/**
 * Warns when buildings or corridors have changed since the current design ran,
 * so the map's drops and the BOQ are never silently trusted while stale. Offers
 * a one-click re-run that reuses the design's own saved settings (Pilot mode,
 * reach limits and all), falling back to a Design-panel prompt for legacy runs
 * saved before full-rule storage.
 */
export default function StaleDesignBanner(
  { projectId, refreshKey, onRerun }:
  { projectId: string; refreshKey: number; onRerun: () => void },
) {
  const [s, setS] = useState<Awaited<
    ReturnType<typeof api.designStaleness>> | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.designStaleness(projectId).then(setS).catch(() => setS(null))
  }, [projectId, refreshKey])

  if (!s || !s.has_design || !s.stale) return null

  const bits: string[] = []
  if (s.buildings_changed)
    bits.push(`${s.buildings_changed} building${s.buildings_changed === 1 ? '' : 's'}`)
  if (s.corridors_changed)
    bits.push(`${s.corridors_changed} corridor${s.corridors_changed === 1 ? '' : 's'}`)

  async function rerun() {
    setBusy(true); setErr(null)
    try {
      await api.rerunDesign(projectId)
      onRerun()
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Re-run failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pointer-events-auto rounded border-l-2 border-amber-500 bg-white px-2.5 py-2 shadow-md">
      <p className="font-mono text-[10px] uppercase tracking-wide text-amber-600">
        Design out of date
      </p>
      <p className="mt-1 text-[11px] text-navy">
        {bits.join(' and ')} changed since the last run — drops and BOQ are stale.
      </p>
      {s.can_rerun ? (
        <button
          className="btn-primary mt-1.5 w-full py-1 text-[10px] disabled:opacity-40"
          disabled={busy} onClick={() => void rerun()}>
          {busy ? 'Re-running…' : 'Re-run design (same settings)'}
        </button>
      ) : (
        <p className="mt-1 text-[10px] text-steel">
          Re-run once from the Design panel to refresh — then re-runs are one click.
        </p>
      )}
      {err && <p className="mt-1 text-[10px] text-red-600">{err}</p>}
    </div>
  )
}
