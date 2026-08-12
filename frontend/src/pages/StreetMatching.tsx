import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import maplibregl, { type StyleSpecification } from 'maplibre-gl'
import { api, type Candidates, type MatchingQueue, type RecordedStreet }
  from '../api/client'
import MediaGallery from '../components/MediaGallery'


/**
 * Glyphs are served from the app's own /public/fonts, generated with fontnik.
 * MapLibre requires PBF glyph ranges for any symbol layer and fails silently
 * without them — no error, no text. Self-hosting removes the dependency on an
 * external glyph server entirely, which a deployable product needs anyway.
 * VITE_GLYPHS_URL overrides the location if you move them behind a CDN.
 */
const GLYPHS = (import.meta.env.VITE_GLYPHS_URL as string | undefined)
  ?? '/fonts/{fontstack}/{range}.pbf'

// Must match the directory under /public/fonts and the name inside the PBF.
const FONT_STACK = ['Liberation Sans Regular']

const PLAIN: StyleSpecification = {
  version: 8, glyphs: GLYPHS, sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#F2F6FB' } }],
}
const STYLE_URL = import.meta.env.VITE_BASEMAP_STYLE_URL as string | undefined

/**
 * Length ranks the shortlist; it does not identify the road. Tested against
 * streets named in both sources it resolved 0 of 5 uniquely, so this screen
 * exists to put the decision in front of a person with the map.
 */
export default function StreetMatching() {
  const { id = '' } = useParams()
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)

  const [queue, setQueue] = useState<MatchingQueue | null>(null)
  const [active, setActive] = useState<RecordedStreet | null>(null)
  const [cands, setCands] = useState<Candidates | null>(null)
  const [hover, setHover] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const reload = useCallback(() => {
    api.matchingQueue(id).then(setQueue).catch((e) => setError(e.message))
  }, [id])
  useEffect(reload, [reload])

  useEffect(() => {
    if (!container.current || map.current) return
    const m = new maplibregl.Map({
      container: container.current, style: STYLE_URL || PLAIN,
      center: [7.441, 9.049], zoom: 13.5,
      attributionControl: { compact: true },
    })
    map.current = m
    m.addControl(new maplibregl.NavigationControl(), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    m.on('load', async () => {
      ready.current = true
      const all = await api.streetsGeoJSON(id)
      m.addSource('all', { type: 'geojson',
        data: { type: 'FeatureCollection', features: all.features } })
      m.addSource('cands', { type: 'geojson',
        data: { type: 'FeatureCollection', features: [] } })
      m.addLayer({ id: 'all-line', type: 'line', source: 'all',
        paint: {
          'line-color': ['match', ['get', 'name_state'],
            'confirmed', '#00C9A7', 'identified', '#4BAADF', '#A8D4EE'],
          'line-width': ['match', ['get', 'name_state'], 'confirmed', 3, 2],
        } })
      // Existing names are the context that makes a match decidable.
      m.addLayer({ id: 'all-label', type: 'symbol', source: 'all',
        minzoom: 10.5,
        filter: ['get', 'named'],
        layout: { 'symbol-placement': 'line', 'text-field': ['get', 'name'],
                  'text-font': FONT_STACK,
                  'text-size': 11, 'text-max-angle': 40 },
        paint: { 'text-color': '#1A2E72', 'text-halo-color': '#ffffff',
                 'text-halo-width': 2 } })
      m.addLayer({ id: 'cand-line', type: 'line', source: 'cands',
        paint: {
          'line-color': ['case', ['boolean', ['feature-state', 'hover'], false],
            '#00C9A7', '#1A6FA8'],
          'line-width': ['case', ['boolean', ['feature-state', 'hover'], false],
            8, 5],
        } })
      m.addLayer({ id: 'cand-label', type: 'symbol', source: 'cands',
        layout: { 'symbol-placement': 'line-center', 'text-field': ['get', 'code'],
                  'text-font': FONT_STACK, 'text-size': 11 },
        paint: { 'text-color': '#0D1B4B', 'text-halo-color': '#fff',
                 'text-halo-width': 2 } })
      m.on('click', 'cand-line', (e) => {
        const f = e.features?.[0]
        if (f?.properties?.street_id) void confirm(String(f.properties.street_id))
      })
      m.on('mouseenter', 'cand-line', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'cand-line', () => { m.getCanvas().style.cursor = '' })
    })
    return () => { m.remove(); map.current = null; ready.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // Draw the shortlist whenever it changes.
  useEffect(() => {
    const m = map.current
    if (!m || !ready.current || !cands) return
    void (async () => {
      const all = await api.streetsGeoJSON(id)
      const ids = new Set(cands.candidates.map((c) => c.street_id))
      const feats = all.features.filter((f) => ids.has(String(f.id))).map((f) => {
        const c = cands.candidates.find((x) => x.street_id === String(f.id))!
        return { ...f, properties: { ...f.properties, street_id: f.id,
                                     code: c.street_code, delta: c.delta_pct } }
      })
      const src = m.getSource('cands') as maplibregl.GeoJSONSource
      src.setData({ type: 'FeatureCollection', features: feats })
      const pts: number[][] = []
      const walk = (x: unknown): void => {
        if (Array.isArray(x) && typeof x[0] === 'number') pts.push(x as number[])
        else if (Array.isArray(x)) x.forEach(walk)
      }
      feats.forEach((f) => walk((f.geometry as GeoJSON.LineString).coordinates))
      if (pts.length) {
        const b = pts.reduce((acc, p) => acc.extend([p[0], p[1]]),
          new maplibregl.LngLatBounds([pts[0][0], pts[0][1]], [pts[0][0], pts[0][1]]))
        m.fitBounds(b, { padding: 80, duration: 300 })
      }
    })()
  }, [cands, id])

  async function select(rec: RecordedStreet) {
    setActive(rec); setCands(null); setError(null)
    try { setCands(await api.matchCandidates(id, rec.id)) }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not load candidates.') }
  }

  async function confirm(streetId: string) {
    if (!active) return
    setSaving(true); setError(null)
    try {
      await api.confirmMatch(id, active.id, streetId)
      setActive(null); setCands(null); reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not confirm the match.')
    } finally { setSaving(false) }
  }

  const pending = queue?.streets.filter((s) => s.match_status !== 'confirmed') ?? []
  const done = queue?.streets.filter((s) => s.match_status === 'confirmed') ?? []

  return (
    <div className="flex h-full">
      <aside className="w-96 shrink-0 overflow-auto border-r border-pale p-5">
        <Link to={`/projects/${id}`} className="font-mono text-[11px] uppercase text-brand">
          ← Map
        </Link>
        <h1 className="mt-2 text-xl text-navy">Street name matching</h1>
        {queue && (
          <p className="text-sm text-steel">
            {queue.confirmed} of {queue.total} matched · {queue.unmatched} outstanding
          </p>
        )}

        <p className="mt-3 rounded border-l-2 border-teal bg-lightgrey px-3 py-2 text-xs text-navy">
          Recorded length ranks the shortlist. It does not identify the road —
          on streets named in both sources it resolved none of five uniquely.
          Confirm against the map before matching.
        </p>

        {error && (
          <p className="mt-3 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-xs">
            {error}
          </p>
        )}

        {active && cands && (
          <div className="card mt-4 p-3">
            <p className="font-mono text-[10px] uppercase text-brand">Matching</p>
            <p className="text-navy">{active.name}</p>
            <p className="font-mono text-xs text-steel">
              recorded {active.recorded_length_m?.toFixed(0) ?? '—'} m
            </p>
            {/* Photos are attached to the recorded street itself (see
                app/import_existing_network_survey.py) — most recorded
                streets won't have any, hence the default hideWhenEmpty. */}
            <MediaGallery projectId={id} entityType="recorded_street" entityId={active.id} />
            <p className={`mt-1 rounded px-2 py-1 text-[11px] ${
              cands.strong_name_matches > 0
                ? 'bg-lightgrey text-navy' : 'bg-lightgrey text-steel'}`}>
              {cands.note}
            </p>
            <div className="mt-2 space-y-1">
              {cands.candidates.map((c) => (
                <button key={c.street_id}
                        className={`w-full rounded px-2 py-1.5 text-left text-xs
                          ${c.name_match === 'strong' ? 'border-l-2 border-teal bg-lightgrey' : ''}
                          ${hover === c.street_id ? 'bg-lightgrey' : ''}`}
                        onMouseEnter={() => setHover(c.street_id)}
                        onMouseLeave={() => setHover(null)}
                        disabled={saving}
                        onClick={() => void confirm(c.street_id)}>
                  <div className="flex justify-between">
                    <span className="font-mono text-[10px] text-brand">{c.street_code}</span>
                    <span className="text-steel">
                      {c.length_m} m
                      {c.delta_pct != null && !c.crosses_boundary && (
                        <b className={Math.abs(c.delta_pct) <= 10 ? 'ml-1 text-teal'
                          : 'ml-1 text-midgrey'}>
                          {c.delta_pct > 0 ? '+' : ''}{c.delta_pct}%
                        </b>
                      )}
                    </span>
                  </div>
                  {c.existing_name && (
                    <div className="mt-0.5 flex items-center gap-1">
                      <span className={c.name_match === 'strong'
                        ? 'text-navy' : 'text-steel'}>{c.existing_name}</span>
                      {c.name_similarity != null && (
                        <span className={`badge ${c.name_match === 'strong'
                          ? 'bg-teal text-white' : 'bg-lightgrey text-steel'}`}>
                          {Math.round(c.name_similarity * 100)}% name
                        </span>
                      )}
                    </div>
                  )}
                  {c.crosses_boundary && (
                    <div className="mt-0.5 text-[10px] text-midgrey">
                      crosses the district boundary — length here is the Wuye
                      portion only
                    </div>
                  )}
                </button>
              ))}
            </div>
            <button className="btn-ghost mt-2 w-full py-1 text-xs"
                    onClick={() => { setActive(null); setCands(null) }}>
              Cancel
            </button>
          </div>
        )}

        <h2 className="label mt-5">Awaiting a match ({pending.length})</h2>
        <div className="space-y-1">
          {pending.map((s) => (
            <button key={s.id}
                    className={`flex w-full justify-between rounded px-2 py-1.5 text-left text-xs
                      ${active?.id === s.id ? 'bg-lightgrey' : 'hover:bg-lightgrey'}`}
                    onClick={() => void select(s)}>
              <span className="text-navy">{s.name}</span>
              <span className="font-mono text-[10px] text-steel">
                {s.recorded_length_m?.toFixed(0) ?? '—'} m
              </span>
            </button>
          ))}
        </div>

        {done.length > 0 && (
          <>
            <h2 className="label mt-5">Matched ({done.length})</h2>
            <div className="space-y-0.5">
              {done.map((s) => (
                <div key={s.id} className="flex justify-between px-2 py-1 text-xs">
                  <span className="text-steel">{s.name}</span>
                  <span className="font-mono text-[10px] text-teal">
                    {s.length_delta_pct != null
                      ? `${s.length_delta_pct > 0 ? '+' : ''}${s.length_delta_pct}%`
                      : '✓'}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}
      </aside>

      <div className="relative min-w-0 flex-1">
        <div ref={container} className="absolute inset-0" />
        {!active && (
          <div className="pointer-events-none absolute left-1/2 top-6 -translate-x-1/2 rounded bg-white/90 px-3 py-2 text-xs text-steel">
            Select a recorded street to see candidate roads
          </div>
        )}
      </div>
    </div>
  )
}
