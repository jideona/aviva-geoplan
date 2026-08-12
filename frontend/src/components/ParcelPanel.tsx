import { useEffect, useState } from 'react'
import { api, type ParcelListing, type ParcelSummary } from '../api/client'
import ParcelNamingPanel from './ParcelNamingPanel'

interface Disagreement {
  parcel: string; workbook_estate: string
  markers: number; workbook_buildings: number; footprints_inside: number
}

interface Props {
  projectId: string
  onChanged: () => void
  selectedParcel: string | null
  onParcelSelect: (id: string | null) => void
}

export default function ParcelPanel(
  { projectId, onChanged, selectedParcel, onParcelSelect }: Props,
) {
  const [summary, setSummary] = useState<ParcelSummary | null>(null)
  const [listing, setListing] = useState<ParcelListing | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [issues, setIssues] = useState<Disagreement[]>([])

  const load = async () => {
    await Promise.allSettled([
      api.parcelSummary(projectId).then(setSummary),
      api.listParcels(projectId).then(setListing),
    ])
  }
  useEffect(() => { void load() }, [projectId])

  async function run(kind: 'perimeters' | 'markers' | 'names', file: File) {
    setBusy(kind); setError(null); setNote(null)
    try {
      const r = kind === 'perimeters' ? await api.importPerimeters(projectId, file)
        : kind === 'names' ? await api.importNamePoints(projectId, file)
        : await api.importMarkers(projectId, file)
      setNote(JSON.stringify(r))
      await load(); onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed.')
    } finally { setBusy(null) }
  }

  async function attach() {
    setBusy('attach'); setError(null)
    try {
      const r = await api.attachUnits(projectId)
      setNote(r.note); setIssues(r.disagreements ?? [])
      await load(); onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not attach units.')
    } finally { setBusy(null) }
  }

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Estate perimeters</h2>
      <p className="mb-2 text-[11px] text-steel">
        The property boundary the network is built to. Drops run from here to
        the unit at signup.
      </p>

      <label className="btn-ghost w-full cursor-pointer">
        {busy === 'perimeters' ? 'Importing…' : 'Perimeters (KML/KMZ)'}
        <input type="file" className="hidden" accept=".kml,.kmz"
               disabled={busy !== null}
               onChange={(e) => { const f = e.target.files?.[0]
                 if (f) void run('perimeters', f); e.target.value = '' }} />
      </label>
      <label className="btn-ghost mt-1 w-full cursor-pointer">
        {busy === 'markers' ? 'Importing…' : 'Building count markers (KML/KMZ)'}
        <input type="file" className="hidden" accept=".kml,.kmz"
               disabled={busy !== null}
               onChange={(e) => { const f = e.target.files?.[0]
                 if (f) void run('markers', f); e.target.value = '' }} />
      </label>
      <label className="btn-ghost mt-1 w-full cursor-pointer">
        {busy === 'names' ? 'Importing…' : 'Estate name points (KML/KMZ)'}
        <input type="file" className="hidden" accept=".kml,.kmz"
               disabled={busy !== null}
               onChange={(e) => { const f = e.target.files?.[0]
                 if (f) void run('names', f); e.target.value = '' }} />
      </label>
      <p className="mt-1 text-[10px] text-steel">
        Labelled points inside a perimeter name it directly. An existing real
        name is never overwritten.
      </p>

      <button className="btn-primary mt-1 w-full py-1 text-xs"
              disabled={busy !== null} onClick={attach}>
        {busy === 'attach' ? 'Matching…' : 'Attach workbook units to parcels'}
      </button>

      {error && (
        <p className="mt-2 rounded border-l-2 border-brand bg-lightgrey px-2 py-1 text-xs">
          {error}
        </p>
      )}
      {note && (
        <p className="mt-2 rounded border-l-2 border-teal bg-lightgrey px-2 py-1 text-[10px] text-navy">
          {note}
        </p>
      )}

      {summary?.available && (
        <div className="card mt-2 p-3 text-xs">
          <Row label="Parcels" value={summary.parcels} />
          <Row label="Buildings inside" value={
            `${summary.buildings_inside_parcels?.toLocaleString()} / ${
              summary.buildings_total?.toLocaleString()} (${summary.coverage_pct}%)`} />
          <Row label="Parcels with units" value={summary.parcels_with_units} />
          <Row label="Units attached" value={summary.units_total} strong />
        </div>
      )}

      <ParcelNamingPanel projectId={projectId} listing={listing}
                         selectedId={selectedParcel}
                         onSelect={onParcelSelect}
                         onChanged={() => { void load(); onChanged() }} />

      {issues.length > 0 && (
        <div className="mt-2 rounded border-l-2 border-brand bg-lightgrey p-2 text-[10px]">
          <p className="font-mono uppercase tracking-wide text-navy">
            Count disagreements ({issues.length})
          </p>
          <p className="mt-1 text-steel">
            Perimeter survey and workbook differ. Both retained — neither is
            assumed correct.
          </p>
          <div className="mt-1 max-h-40 overflow-auto">
            {issues.map((d) => (
              <div key={d.parcel} className="flex justify-between py-0.5">
                <span className="truncate pr-2 text-navy">{d.parcel}</span>
                <span className="shrink-0 font-mono text-steel">
                  {d.markers} mk · {d.workbook_buildings} wb · {d.footprints_inside} fp
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function Row({ label, value, strong }:
             { label: string; value: unknown; strong?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-steel">{label}</span>
      <span className={strong ? 'font-mono text-navy' : 'font-mono text-steel'}>
        {typeof value === 'number' ? value.toLocaleString() : String(value ?? '—')}
      </span>
    </div>
  )
}
