import { useEffect, useState } from 'react'
import { api, type PremisesModel, type SurveyCoverage } from '../api/client'

const LABELS: Record<string, string> = {
  single: '1 unit', small_multi: '2–3 units', block: '4–8 units',
  large_block: '9–15 units', tower: '16+ units', unknown: 'unknown',
}

export default function PremisesModelPanel({ projectId }: { projectId: string }) {
  const [model, setModel] = useState<PremisesModel | null>(null)
  const [coverage, setCoverage] = useState<SurveyCoverage | null>(null)
  useEffect(() => {
    api.premisesModel(projectId).then(setModel).catch(() => {})
    api.coverage(projectId).then(setCoverage).catch(() => {})
  }, [projectId])

  if (!model) return null

  if (!model.available) {
    return (
      <div className="mt-6 border-t border-lightgrey pt-4">
        <h2 className="label">Premises model</h2>
        <p className="text-xs text-steel">{model.reason}</p>
      </div>
    )
  }

  const bands = model.bands ?? {}
  const bias = model.sampling_bias
  const total = model.district_total

  return (
    <div className="mt-6 border-t border-lightgrey pt-4">
      <h2 className="label">Premises model</h2>
      <p className="text-xs text-steel">
        {model.observations?.toLocaleString()} independent counts covering{' '}
        {model.buildings_covered?.toLocaleString()} buildings ·{' '}
        <span className="font-mono">{model.version}</span>
      </p>

      <p className="mt-1 text-[10px] text-steel">
        n is independent counts; ×N is buildings per count. A tight interval at
        high ×N reflects uniform estate design, not corroboration.
      </p>
      <div className="card mt-2 p-3 text-xs">
        {Object.entries(bands).map(([key, b]) => (
          <div key={key} className="flex items-center justify-between py-0.5">
            <span className="text-steel">
              {LABELS[key] ?? key}
              {!b.well_evidenced && (
                <span className="ml-1 text-[10px] text-midgrey">(thin sample)</span>
              )}
            </span>
            <span className="font-mono text-navy">
              med {b.median} · n={b.sample_size}
              {b.replication > 2 && (
                <span className="ml-1 text-midgrey">×{b.replication}</span>
              )}
            </span>
          </div>
        ))}
      </div>

      {coverage?.available && (
        <div className={`mt-3 rounded border-l-2 p-3 text-xs ${
          coverage.spatially_representative
            ? 'border-teal bg-lightgrey' : 'border-brand bg-lightgrey'}`}>
          <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
            Spatial coverage
          </p>
          <div className="mt-1 flex justify-between">
            <span className="text-steel">Buildings in surveyed areas</span>
            <span className="font-mono text-navy">
              {coverage.buildings_in_surveyed_areas?.toLocaleString()} /{' '}
              {coverage.buildings_total?.toLocaleString()} ({coverage.coverage_pct}%)
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-steel">Areas with no observations</span>
            <span className="font-mono text-navy">
              {coverage.cells_without_coverage} / {coverage.cells_total}
            </span>
          </div>
          <p className="mt-1 text-steel">{coverage.note}</p>
        </div>
      )}

      {bias && (
        <div className={`mt-3 rounded border-l-2 p-3 text-xs ${
          bias.representative ? 'border-teal bg-lightgrey' : 'border-brand bg-lightgrey'}`}>
          <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
            Sampling
          </p>
          <p className="mt-1 text-steel">{bias.note}</p>
        </div>
      )}

      {total && !total.available && (
        <p className="mt-2 text-xs text-steel">
          <b className="text-navy">No district premises total.</b> {total.reason}
        </p>
      )}
      {total?.available && (
        <div className="card mt-2 p-3 text-xs">
          <div className="flex justify-between">
            <span className="text-steel">District premises</span>
            <span className="font-mono text-navy">
              {total.premises_estimate?.toLocaleString()}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-steel">Range</span>
            <span className="font-mono text-steel">
              {total.interval_low?.toLocaleString()}–{total.interval_high?.toLocaleString()}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
