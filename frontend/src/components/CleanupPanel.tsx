import { useState } from 'react'
import { api } from '../api/client'

type Preview = { type: string; features: GeoJSON.Feature[] } | null

/**
 * Bulk removal of non-building footprints — tiny slivers and round vegetation
 * blobs (tree canopies, tanks) that Overture drags in. Preview draws the
 * candidates in magenta before anything is touched; Apply excludes them
 * (reversible via the register's Restore).
 */
export default function CleanupPanel(
  { projectId, onPreview, onChanged }:
  { projectId: string; onPreview: (fc: Preview) => void; onChanged: () => void },
) {
  const [open, setOpen] = useState(false)
  const [minArea, setMinArea] = useState('10')
  const [circ, setCirc] = useState('0.88')
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null)
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.cleanupBuildings>> | null>(null)
  const [err, setErr] = useState<string | null>(null)

  async function run(dryRun: boolean) {
    setBusy(dryRun ? 'preview' : 'apply'); setErr(null)
    try {
      const r = await api.cleanupBuildings(projectId, Number(minArea) || 0, Number(circ) || 1, dryRun)
      setRes(r)
      if (dryRun) onPreview(r.preview ?? null)
      else { onPreview(null); onChanged() }
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Cleanup failed.')
    } finally { setBusy(null) }
  }

  return (
    <div className="pointer-events-auto rounded bg-white px-2.5 py-2 shadow-md">
      <button className="flex w-full items-center justify-between"
              onClick={() => setOpen((v) => !v)}>
        <span className="font-mono text-[10px] uppercase tracking-wide text-brand">Footprint cleanup</span>
        <span className="font-mono text-[10px] text-steel">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div className="mt-1.5">
          <p className="text-[10px] text-steel">
            Removes tiny slivers and round vegetation blobs (not rectangular buildings).
          </p>
          <div className="mt-1.5 flex items-center gap-2">
            <label className="text-[10px] text-navy">Min m²</label>
            <input className="field w-14 py-0.5 text-[11px]" value={minArea}
                   onChange={(e) => setMinArea(e.target.value)} inputMode="decimal" />
            <label className="text-[10px] text-navy">Roundness ≥</label>
            <input className="field w-14 py-0.5 text-[11px]" value={circ}
                   onChange={(e) => setCirc(e.target.value)} inputMode="decimal" />
          </div>
          <div className="mt-1.5 flex gap-1">
            <button className="btn-ghost flex-1 py-1 text-[10px] disabled:opacity-40"
                    disabled={busy !== null} onClick={() => void run(true)}>
              {busy === 'preview' ? 'Previewing…' : 'Preview'}
            </button>
            <button className="btn-primary flex-1 py-1 text-[10px] disabled:opacity-40"
                    disabled={busy !== null || !res || !res.candidates}
                    onClick={() => void run(false)}>
              {busy === 'apply' ? 'Removing…'
                : res && res.dry_run ? `Remove ${res.candidates}` : 'Remove'}
            </button>
          </div>
          {res && (
            <p className="mt-1.5 text-[10px] text-navy">
              {res.dry_run
                ? `${res.candidates} to remove — ${res.tiny} tiny, ${res.round} round (magenta)`
                : `Removed ${res.excluded}. Restore from the register if needed.`}
            </p>
          )}
          {err && <p className="mt-1 text-[10px] text-red-600">{err}</p>}
        </div>
      )}
    </div>
  )
}
