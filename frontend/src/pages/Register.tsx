import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type Attribution, type RegisterPage, type RegisterSummary }
  from '../api/client'

const PAGE = 100

const VERIFICATION = ['imported', 'ai_detected', 'desk_verified', 'field_observed',
  'field_measured', 'customer_confirmed', 'authority_verified',
  'engineer_approved', 'as_built_confirmed']

const PURPOSES = [
  { value: 'internal', label: 'Internal use' },
  { value: 'client_review', label: 'Client review (under NDA)' },
  { value: 'commercial', label: 'Commercial delivery' },
]

export default function Register() {
  const { id = '' } = useParams()
  const [page, setPage] = useState<RegisterPage | null>(null)
  const [summary, setSummary] = useState<RegisterSummary | null>(null)
  const [attribution, setAttribution] = useState<Attribution | null>(null)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('area')
  const [descending, setDescending] = useState(true)
  const [search, setSearch] = useState('')
  const [verification, setVerification] = useState('')
  const [unassigned, setUnassigned] = useState(false)
  const [needsReview, setNeedsReview] = useState(false)
  const [purpose, setPurpose] = useState('internal')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const params = useMemo(() => {
    const p = new URLSearchParams()
    if (search.trim()) p.set('search', search.trim())
    if (verification) p.set('verification_state', verification)
    if (unassigned) p.set('unassigned_only', 'true')
    if (needsReview) p.set('needs_review', 'true')
    return p
  }, [search, verification, unassigned, needsReview])

  const load = useCallback(() => {
    setLoading(true)
    const p = new URLSearchParams(params)
    p.set('sort', sort); p.set('descending', String(descending))
    p.set('limit', String(PAGE)); p.set('offset', String(offset))
    api.register(id, p).then(setPage).catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id, params, sort, descending, offset])

  useEffect(load, [load])
  useEffect(() => { setOffset(0) }, [params, sort, descending])
  useEffect(() => {
    api.registerSummary(id).then(setSummary).catch(() => {})
  }, [id])
  useEffect(() => {
    api.attribution(id, purpose).then(setAttribution).catch(() => {})
  }, [id, purpose])

  async function download(fmt: 'csv' | 'xlsx' | 'geojson') {
    setError(null)
    const p = new URLSearchParams(params)
    p.set('purpose', purpose)
    try {
      await api.download(api.exportUrl(id, fmt, p), `building_register.${fmt}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed.')
    }
  }

  const blocked = attribution?.blocked ?? false

  return (
    <div className="p-6">
      <Link to={`/projects/${id}`} className="font-mono text-[11px] uppercase text-brand">
        ← Map
      </Link>
      <h1 className="mt-2 text-2xl text-navy">Building register</h1>

      {summary && (
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-6">
          <Stat label="Buildings" value={summary.buildings.toLocaleString()} />
          <Stat label="Assigned" value={`${summary.assigned_pct}%`}
                sub={`${summary.assigned_to_street.toLocaleString()} of ${summary.buildings.toLocaleString()}`} />
          <Stat label="Unassigned" value={summary.unassigned.toLocaleString()} />
          <Stat label="Streets" value={summary.streets.toLocaleString()}
                sub={`${summary.streets_unnamed} unnamed`} />
          <Stat label="Median footprint"
                value={summary.median_footprint_sqm ? `${summary.median_footprint_sqm} m²` : '—'} />
          <Stat label="Surveyed" value={summary.buildings_surveyed.toLocaleString()}
                sub={summary.buildings_surveyed ? undefined : 'no field data yet'} />
        </div>
      )}

      {summary && summary.buildings_surveyed === 0 && (
        <p className="mt-3 rounded border-l-2 border-teal bg-lightgrey px-3 py-2 text-xs text-navy">
          Premises counts are absent because the estimation model has no survey
          data to calibrate against. Footprint geometry alone does not determine
          how many serviceable units a building contains.
        </p>
      )}

      <div className="card mt-5 flex flex-wrap items-end gap-3 p-4">
        <div className="min-w-48 flex-1">
          <label className="label">Search</label>
          <input className="field" placeholder="Building code or street"
                 value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div>
          <label className="label">Verification</label>
          <select className="field" value={verification}
                  onChange={(e) => setVerification(e.target.value)}>
            <option value="">Any</option>
            {VERIFICATION.map((v) => (
              <option key={v} value={v}>{v.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
        <label className="flex items-center gap-2 pb-2 text-sm text-navy">
          <input type="checkbox" checked={unassigned}
                 onChange={(e) => setUnassigned(e.target.checked)} />
          Unassigned only
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm text-navy">
          <input type="checkbox" checked={needsReview}
                 onChange={(e) => setNeedsReview(e.target.checked)} />
          Needs review
        </label>
      </div>

      <div className="card mt-3 flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label">Export purpose</label>
          <select className="field" value={purpose}
                  onChange={(e) => setPurpose(e.target.value)}>
            {PURPOSES.map((p) => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
        </div>
        <button className="btn-primary" disabled={blocked}
                onClick={() => void download('xlsx')}>Excel</button>
        <button className="btn-ghost" disabled={blocked}
                onClick={() => void download('csv')}>CSV</button>
        <button className="btn-ghost" disabled={blocked}
                onClick={() => void download('geojson')}>GeoJSON</button>

        {attribution && (
          <div className={`w-full rounded border-l-2 px-3 py-2 text-xs ${
            blocked ? 'border-brand bg-lightgrey' : 'border-teal bg-lightgrey'}`}>
            {blocked ? (
              <p className="text-navy"><b>Export blocked.</b> {attribution.reason}</p>
            ) : (
              <p className="text-steel">
                Cleared for {purpose.replace(/_/g, ' ')}. Attribution included in
                every export.
              </p>
            )}
            <div className="mt-1 text-steel">
              {attribution.attribution.map((line) => <div key={line}>{line}</div>)}
            </div>
          </div>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm">
          {error}
        </p>
      )}

      <div className="card mt-4 overflow-auto">
        <table className="w-full text-left text-xs">
          <thead className="bg-navy text-white">
            <tr>
              {[['code', 'Building'], ['', 'Street'], ['area', 'Area m²'],
                ['type', 'Type'], ['', 'Premises'], ['confidence', 'Confidence'],
                ['', 'Source'], ['verification', 'Verification']].map(([key, label]) => (
                <th key={label} className="px-3 py-2 font-mono text-[10px] uppercase">
                  {key ? (
                    <button onClick={() => {
                      if (sort === key) setDescending(!descending)
                      else { setSort(key); setDescending(true) }
                    }}>
                      {label}{sort === key ? (descending ? ' ↓' : ' ↑') : ''}
                    </button>
                  ) : label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page?.rows.map((r, i) => (
              <tr key={r.id} className={i % 2 ? 'bg-lightgrey/40' : ''}>
                <td className="px-3 py-1.5 font-mono text-[11px] text-navy">
                  {r.building_code ?? '—'}
                </td>
                <td className="px-3 py-1.5">
                  {r.street_name ?? <span className="text-midgrey">unassigned</span>}
                  {r.street_code && (
                    <span className="ml-1 font-mono text-[10px] text-brand">
                      {r.street_code}
                    </span>
                  )}
                </td>
                <td className="px-3 py-1.5 font-mono">{r.footprint_area_sqm.toFixed(0)}</td>
                <td className="px-3 py-1.5">{r.building_type.replace(/_/g, ' ')}</td>
                <td className="px-3 py-1.5 font-mono">
                  {r.units_surveyed != null
                    ? <b className="text-navy">{r.units_surveyed}</b>
                    : r.premises_estimated != null
                      ? <span className="text-steel">~{r.premises_estimated}</span>
                      : <span className="text-midgrey">—</span>}
                </td>
                <td className="px-3 py-1.5 font-mono" title={r.assignment_reason ?? ''}>
                  {r.assignment_confidence != null ? (
                    <span className={r.assignment_confidence >= 0.7 ? 'text-teal'
                      : r.assignment_confidence >= 0.4 ? 'text-brand' : 'text-midgrey'}>
                      {r.assignment_confidence.toFixed(2)}
                    </span>
                  ) : '—'}
                </td>
                <td className="px-3 py-1.5 text-steel">{r.source_dataset ?? '—'}</td>
                <td className="px-3 py-1.5">
                  <span className="badge bg-lightgrey text-steel">
                    {r.verification_state.replace(/_/g, ' ')}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <p className="p-4 text-sm text-steel">Loading…</p>}
        {page && page.total === 0 && !loading && (
          <p className="p-8 text-center text-sm text-steel">
            No buildings match this filter.
          </p>
        )}
      </div>

      {page && page.total > PAGE && (
        <div className="mt-3 flex items-center justify-between text-sm">
          <span className="text-steel">
            {offset + 1}–{Math.min(offset + PAGE, page.total)} of{' '}
            {page.total.toLocaleString()}
          </span>
          <div className="flex gap-2">
            <button className="btn-ghost py-1" disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Previous
            </button>
            <button className="btn-ghost py-1"
                    disabled={offset + PAGE >= page.total}
                    onClick={() => setOffset(offset + PAGE)}>
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-3">
      <p className="font-mono text-[10px] uppercase tracking-wide text-brand">{label}</p>
      <p className="mt-1 text-xl text-navy">{value}</p>
      {sub && <p className="text-[11px] text-steel">{sub}</p>}
    </div>
  )
}
