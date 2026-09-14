import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type FieldActivityItem, type FieldActivityPage } from '../api/client'

const PAGE = 50

const ENTITY_LABEL: Record<string, string> = {
  building: 'Building', manhole: 'Manhole', building_photo: 'Building photo',
  survey_route: 'Cable route', media_asset: 'Photo / video',
}

const ACTION_LABEL: Record<string, string> = {
  create_manual: 'Drew building', edit_geometry: 'Edited footprint',
  field_update: 'Updated attributes', exclude: 'Excluded', restore: 'Restored',
  capture_manhole: 'Captured manhole', assess_manhole: 'Assessed condition',
  capture_building_photo: 'Captured photo point', capture_route: 'Recorded route',
  upload_media: 'Uploaded media',
}

function summarise(item: FieldActivityItem): string {
  if (!item.changes || Object.keys(item.changes).length === 0) return '—'
  return Object.entries(item.changes)
    .map(([field, { before, after }]) => `${field}: ${before ?? '—'} → ${after ?? '—'}`)
    .join(', ')
}

export default function FieldActivity() {
  const { id = '' } = useParams()
  const [page, setPage] = useState<FieldActivityPage | null>(null)
  const [surveyors, setSurveyors] = useState<string[]>([])
  const [offset, setOffset] = useState(0)
  const [surveyor, setSurveyor] = useState('')
  const [entityType, setEntityType] = useState('')
  const [since, setSince] = useState('')
  const [until, setUntil] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const params = useMemo(() => {
    const p = new URLSearchParams()
    if (surveyor) p.set('surveyor', surveyor)
    if (entityType) p.set('entity_type', entityType)
    if (since) p.set('since', new Date(since).toISOString())
    if (until) p.set('until', new Date(until).toISOString())
    return p
  }, [surveyor, entityType, since, until])

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    const p = new URLSearchParams(params)
    p.set('limit', String(PAGE)); p.set('offset', String(offset))
    api.fieldActivity(id, p).then(setPage)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load.'))
      .finally(() => setLoading(false))
  }, [id, params, offset])

  useEffect(load, [load])
  useEffect(() => { setOffset(0) }, [params])
  useEffect(() => {
    api.fieldActivitySurveyors(id).then((r) => setSurveyors(r.surveyors)).catch(() => {})
  }, [id])

  const items = page?.items ?? []
  const total = page?.total ?? 0

  return (
    <div className="p-6">
      <Link to={`/projects/${id}`} className="font-mono text-[11px] uppercase text-brand">
        ← Map
      </Link>
      <h1 className="mt-2 text-2xl text-navy">Field activity</h1>
      <p className="mt-1 max-w-2xl text-sm text-steel">
        Everything that has actually arrived from the field, in the order it
        reached the server — buildings edited on site, manholes and building
        photos captured, cable routes walked, and photos/video confirmed
        uploaded. This reads the same append-only audit trail the platform
        already keeps, so it can be trusted as a record of what was sent, not
        just what the app says it sent.
      </p>

      <div className="card mt-5 flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label">Surveyor</label>
          <select className="field" value={surveyor} onChange={(e) => setSurveyor(e.target.value)}>
            <option value="">Anyone</option>
            {surveyors.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Record type</label>
          <select className="field" value={entityType} onChange={(e) => setEntityType(e.target.value)}>
            <option value="">Any</option>
            {Object.entries(ENTITY_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </div>
        <div>
          <label className="label">Since</label>
          <input type="date" className="field" value={since} onChange={(e) => setSince(e.target.value)} />
        </div>
        <div>
          <label className="label">Until</label>
          <input type="date" className="field" value={until} onChange={(e) => setUntil(e.target.value)} />
        </div>
        {(surveyor || entityType || since || until) && (
          <button className="btn-ghost"
                  onClick={() => { setSurveyor(''); setEntityType(''); setSince(''); setUntil('') }}>
            Clear filters
          </button>
        )}
      </div>

      {error && (
        <p className="mt-3 rounded border-l-2 border-red-500 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </p>
      )}

      <div className="card mt-4 overflow-x-auto">
        <table className="w-full text-left text-[12px]">
          <thead className="border-b border-lightgrey text-[10px] uppercase text-steel">
            <tr>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">Surveyor</th>
              <th className="px-3 py-2">Record</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">What changed</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} className="border-b border-lightgrey last:border-0">
                <td className="whitespace-nowrap px-3 py-2 text-steel">
                  {new Date(item.occurred_at).toLocaleString()}
                </td>
                <td className="px-3 py-2">{item.surveyor ?? '—'}</td>
                <td className="px-3 py-2">{ENTITY_LABEL[item.entity_type] ?? item.entity_type}</td>
                <td className="px-3 py-2">{ACTION_LABEL[item.action] ?? item.action}</td>
                <td className="px-3 py-2">
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    item.change_kind === 'captured'
                      ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>
                    {item.change_kind === 'captured' ? 'NEW' : 'MODIFIED'}
                  </span>
                </td>
                <td className="max-w-xs truncate px-3 py-2 text-steel" title={summarise(item)}>
                  {summarise(item)}
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-steel">
                No field activity matches these filters.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-center justify-between text-[11px] text-steel">
        <span>{total.toLocaleString()} event{total === 1 ? '' : 's'}</span>
        <div className="flex gap-2">
          <button className="btn-ghost" disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</button>
          <button className="btn-ghost" disabled={offset + PAGE >= total}
                  onClick={() => setOffset(offset + PAGE)}>Next</button>
        </div>
      </div>
    </div>
  )
}
