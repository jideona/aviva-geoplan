import { useState } from 'react'
import { api, type ImportSummary, type LicenceSummary } from '../api/client'

interface Props {
  projectId: string
  disabled: boolean
  onImported: () => void
  onPreview: (fc: { type: string; features: GeoJSON.Feature[] } | null) => void
  licence: LicenceSummary | null
}

export default function ImportPanel({ projectId, disabled, onImported, onPreview, licence }: Props) {
  const [busy, setBusy] = useState<string | null>(null)
  const [result, setResult] = useState<ImportSummary | null>(null)
  const [detectResult, setDetectResult] =
    useState<Awaited<ReturnType<typeof api.detectImport>> | null>(null)
  const [previewOnly, setPreviewOnly] = useState(true)
  const [pending, setPending] = useState<unknown | null>(null)   // parsed geojson
  const [error, setError] = useState<string | null>(null)

  async function runDetect(file: File) {
    setError(null); setResult(null); setDetectResult(null); setBusy('detect')
    try {
      const geojson = JSON.parse(await file.text())
      setPending(geojson)
      const r = await api.detectImport(projectId, geojson, previewOnly)
      setDetectResult(r)
      if (previewOnly) {
        onPreview(r.preview ?? null)
      } else {
        onPreview(null); setPending(null); onImported()
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setBusy(null)
    }
  }

  async function commitDetected() {
    if (pending == null) return
    setBusy('detect'); setError(null)
    try {
      const r = await api.detectImport(projectId, pending, false)
      setDetectResult(r); onPreview(null); setPending(null); onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setBusy(null)
    }
  }

  async function clearDetected() {
    setBusy('clear'); setError(null)
    try {
      const r = await api.clearDetected(projectId)
      setDetectResult(null)
      onPreview(null)
      onImported()
      setError(r.deleted > 0
        ? `Removed ${r.deleted} detected building${r.deleted === 1 ? '' : 's'}.`
        : 'No detected buildings to remove.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Clear failed.')
    } finally {
      setBusy(null)
    }
  }

  async function run(kind: 'overture' | 'osm' | 'streets' | 'field', files: FileList) {
    setError(null); setResult(null); setBusy(kind)
    try {
      const summary =
        kind === 'overture' ? await api.importOverture(projectId, files[0])
        : kind === 'osm' ? await api.importOsmRoads(projectId, files[0])
        : kind === 'field'
          ? (await api.importFieldData(projectId, files[0]),
             { created: 0, updated: 0, unchanged: 0, skipped_outside_boundary: 0,
               skipped_too_small: 0, skipped_protected: 0, invalid_geometry: 0,
               licence_classes: {}, datasets: {}, share_alike_present: false })
          : await api.importStreets(projectId, Array.from(files))
      setResult(summary)
      onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Import</h2>

      {disabled && (
        <p className="mb-2 text-xs text-steel">
          Upload a project boundary first — imports are clipped against it.
        </p>
      )}

      <label className={`btn-ghost w-full ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}>
        {busy === 'overture' ? 'Importing…' : 'Overture buildings (GeoJSON)'}
        <input type="file" className="hidden" accept=".geojson,.json"
               disabled={disabled || busy !== null}
               onChange={(e) => { if (e.target.files?.length) void run('overture', e.target.files); e.target.value = '' }} />
      </label>

      <label className={`btn-ghost mt-2 w-full ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}>
        {busy === 'osm' ? 'Importing…' : 'OSM road network (raw XML)'}
        <input type="file" className="hidden" accept=".osm,.xml,map"
               disabled={disabled || busy !== null}
               onChange={(e) => { if (e.target.files?.length) void run('osm', e.target.files); e.target.value = '' }} />
      </label>
      <p className="mt-1 text-xs text-steel">
        Raw OSM XML, not an Overpass GeoJSON or JSON export — those filter to
        named roads and discard most of the network.
      </p>

      <label className={`btn-ghost mt-2 w-full ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}>
        {busy === 'streets' ? 'Importing…' : 'Named centrelines (KML/KMZ)'}
        <input type="file" className="hidden" accept=".kml,.kmz" multiple
               disabled={disabled || busy !== null}
               onChange={(e) => { if (e.target.files?.length) void run('streets', e.target.files); e.target.value = '' }} />
      </label>

      <label className={`btn-ghost mt-2 w-full ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}>
        {busy === 'field' ? 'Importing…' : 'Field survey workbook (.xlsx)'}
        <input type="file" className="hidden" accept=".xlsx"
               disabled={disabled || busy !== null}
               onChange={(e) => { if (e.target.files?.length) void run('field', e.target.files); e.target.value = '' }} />
      </label>
      <p className="mt-1 text-xs text-steel">
        Route-analysis workbook — recorded street names and observed unit counts.
      </p>

      <label className={`btn-ghost mt-2 w-full ${disabled ? 'pointer-events-none opacity-50' : 'cursor-pointer'}`}>
        {busy === 'detect'
          ? (previewOnly ? 'Previewing…' : 'Importing…')
          : 'Detected footprints (GeoJSON)'}
        <input type="file" className="hidden" accept=".geojson,.json"
               disabled={disabled || busy !== null}
               onChange={(e) => { if (e.target.files?.length) void runDetect(e.target.files[0]); e.target.value = '' }} />
      </label>
      <label className="mt-1 flex cursor-pointer items-center gap-2 text-xs text-navy">
        <input type="checkbox" className="h-3 w-3" checked={previewOnly}
               disabled={busy !== null}
               onChange={(e) => setPreviewOnly(e.target.checked)} />
        Preview only — don't import yet (recommended)
      </label>
      <p className="mt-1 text-xs text-steel">
        Auto-detected rooftops from <code>tools/detect_buildings.py</code> (Esri).
        Deduped against the register and each other; preview draws survivors in
        magenta so you can check before committing.
      </p>

      {detectResult && (
        <div className="card mt-3 p-3 text-xs">
          {detectResult.dry_run
            ? <Line label="Would import (new)" value={detectResult.would_import} strong />
            : <Line label="Imported (new)" value={detectResult.imported} strong />}
          <Line label="Duplicates of existing" value={detectResult.duplicates_skipped} />
          <Line label="Merged overlaps" value={detectResult.merged_overlaps} />
          <Line label="Outside boundary" value={detectResult.outside_boundary} />
          <Line label="Invalid / off-size" value={detectResult.invalid} />
          {detectResult.dry_run && detectResult.would_import > 0 && pending != null && (
            <button className="btn-primary mt-2 w-full py-1 text-[11px] disabled:opacity-40"
                    disabled={busy !== null} onClick={() => void commitDetected()}>
              {busy === 'detect' ? 'Importing…'
                : `Import these ${detectResult.would_import} buildings`}
            </button>
          )}
          <p className="mt-2 border-t border-lightgrey pt-2 text-steel">
            {detectResult.note}
          </p>
        </div>
      )}

      <button className="btn-ghost mt-2 w-full text-xs disabled:opacity-40"
              disabled={disabled || busy !== null}
              onClick={() => void clearDetected()}>
        {busy === 'clear' ? 'Clearing…' : 'Clear detected imports'}
      </button>

      <p className="mt-2 text-xs text-steel">
        Overture already deduplicates its sources. Do not import Google Open
        Buildings separately against an Overture load.
      </p>

      {error && (
        <p className="mt-3 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm">
          {error}
        </p>
      )}

      {result && (
        <div className="card mt-3 p-3 text-xs">
          <Line label="Created" value={result.created} strong />
          <Line label="Updated" value={result.updated} />
          <Line label="Unchanged" value={result.unchanged} />
          <Line label="Outside boundary" value={result.skipped_outside_boundary} />
          <Line label="Below minimum size" value={result.skipped_too_small} />
          {result.skipped_protected > 0 && (
            <Line label="Protected — field verified" value={result.skipped_protected} strong />
          )}
          {Object.keys(result.datasets).length > 0 && (
            <div className="mt-2 border-t border-lightgrey pt-2">
              {Object.entries(result.datasets).map(([k, v]) => (
                <Line key={k} label={k} value={v} />
              ))}
            </div>
          )}
        </div>
      )}

      {licence && licence.total > 0 && (
        <div className={`mt-3 rounded border-l-2 p-3 text-xs ${
          licence.blocks_commercial_delivery
            ? 'border-brand bg-lightgrey' : 'border-teal bg-lightgrey'}`}>
          <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
            Licence position
          </p>
          <p className="mt-1 text-navy">
            {licence.share_alike_count.toLocaleString()} of {licence.total.toLocaleString()}
            {' '}buildings ({licence.share_alike_pct}%) are share-alike.
          </p>
          <p className="mt-1 text-steel">{licence.note}</p>
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
