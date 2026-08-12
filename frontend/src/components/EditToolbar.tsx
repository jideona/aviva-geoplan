import { useEffect, useRef, useState } from 'react'
import type maplibregl from 'maplibre-gl'
import { api } from '../api/client'

type Mode = 'none' | 'draw' | 'corridor' | 'move' | 'inspect' | 'exclude'

const SOURCES = [
  { value: 'traced_reference', label: 'Traced from Esri imagery (pilot only)' },
  { value: 'traced_owned', label: 'Traced from Aviva drone' },
  { value: 'field_surveyed', label: 'Field surveyed' },
]

const CORRIDOR_TYPES = [
  { value: 'footpath', label: 'Footpath' },
  { value: 'pathway', label: 'Pathway' },
  { value: 'fence', label: 'Fence line' },
  { value: 'service', label: 'Service way' },
]

interface Props {
  projectId: string
  map: maplibregl.Map | null
  ready: boolean
  onChanged: () => void
  onMoveMode: (on: boolean) => void
}

/**
 * Hand-editing on the map: draw new rooftops, move FDH/FAT markers, and query
 * the Esri imagery date under the cursor. Drawing is deliberately simple —
 * click vertices, double-click or Enter to finish — to avoid a heavy draw
 * dependency.
 */
export default function EditToolbar(
  { projectId, map, ready, onChanged, onMoveMode }: Props,
) {
  const [mode, setMode] = useState<Mode>('none')
  const [source, setSource] = useState('traced_reference')
  const [corridorType, setCorridorType] = useState('footpath')
  const [status, setStatus] = useState<string | null>(null)
  const verts = useRef<[number, number][]>([])
  const [vertCount, setVertCount] = useState(0)
  const modeRef = useRef<Mode>('none')
  modeRef.current = mode
  useEffect(() => { onMoveMode(mode === 'move') }, [mode, onMoveMode])

  // Draw source for the in-progress polygon.
  useEffect(() => {
    if (!map || !ready) return
    if (!map.getSource('draw')) {
      map.addSource('draw', { type: 'geojson', data: EMPTY })
      map.addLayer({ id: 'draw-fill', type: 'fill', source: 'draw',
        paint: { 'fill-color': '#FF6A00', 'fill-opacity': 0.3 } })
      map.addLayer({ id: 'draw-line', type: 'line', source: 'draw',
        paint: { 'line-color': '#FF6A00', 'line-width': 2 } })
      map.addLayer({ id: 'draw-vert', type: 'circle', source: 'draw',
        filter: ['==', '$type', 'Point'],
        paint: { 'circle-radius': 4, 'circle-color': '#FF6A00',
                 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } })
    }
  }, [map, ready])

  function drawData() {
    const src = map?.getSource('draw') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    const feats: GeoJSON.Feature[] = verts.current.map((c) => ({
      type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: c } }))
    if (verts.current.length >= 2) {
      // Corridor is an open polyline; a rooftop closes back to the first point.
      const line = modeRef.current === 'corridor'
        ? verts.current
        : (verts.current.length >= 3
            ? [...verts.current, verts.current[0]] : verts.current)
      feats.push({ type: 'Feature', properties: {},
        geometry: { type: 'LineString', coordinates: line } })
    }
    src.setData({ type: 'FeatureCollection', features: feats })
    setVertCount(verts.current.length)
  }

  useEffect(() => {
    if (!map || !ready) return

    const onClick = (e: maplibregl.MapMouseEvent) => {
      if (modeRef.current === 'inspect') { void identify(e.lngLat.lng, e.lngLat.lat); return }
      if (modeRef.current === 'exclude') {
        const hits = map.queryRenderedFeatures(e.point, { layers: ['buildings-fill'] })
        // UUID ids are dropped by MapLibre (non-numeric), so read the property.
        const bid = hits[0]?.properties?.building_id ?? hits[0]?.id
        if (bid) void exclude(String(bid))
        else setStatus('No building under the click — zoom in and click inside a footprint.')
        return
      }
      if (modeRef.current !== 'draw' && modeRef.current !== 'corridor') return
      verts.current.push([e.lngLat.lng, e.lngLat.lat])
      drawData()
    }
    const onDbl = (e: maplibregl.MapMouseEvent) => {
      if (modeRef.current !== 'draw' && modeRef.current !== 'corridor') return
      e.preventDefault()
      void finish()
    }
    const onKey = (ev: KeyboardEvent) => {
      if (modeRef.current !== 'draw' && modeRef.current !== 'corridor') return
      const min = modeRef.current === 'corridor' ? 2 : 3
      if (ev.key === 'Enter' && verts.current.length >= min) void finish()
      if (ev.key === 'Escape') cancel()
    }
    map.on('click', onClick)
    map.on('dblclick', onDbl)
    window.addEventListener('keydown', onKey)
    return () => { map.off('click', onClick); map.off('dblclick', onDbl)
      window.removeEventListener('keydown', onKey) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, ready])

  async function identify(lon: number, lat: number) {
    setStatus('Reading imagery date…')
    try {
      // Esri World Imagery metadata identify — returns SRC_DATE per location.
      const url = 'https://services.arcgisonline.com/arcgis/rest/services/' +
        'World_Imagery/MapServer/identify?' + new URLSearchParams({
          geometry: `${lon},${lat}`, geometryType: 'esriGeometryPoint',
          sr: '4326', layers: 'all', tolerance: '2', returnGeometry: 'false',
          mapExtent: `${lon - 0.01},${lat - 0.01},${lon + 0.01},${lat + 0.01}`,
          imageDisplay: '800,600,96', f: 'json',
        })
      const r = await fetch(url)
      const j = await r.json()
      const a = j.results?.[0]?.attributes ?? {}
      const date = a.SRC_DATE2 || a.SRC_DATE || a['Source Date'] || 'unknown'
      const src = a.SRC_DESC || a.Source || ''
      const res = a.SRC_RES || a.Resolution || ''
      setStatus(`Imagery: ${date}${src ? ' · ' + src : ''}${res ? ' · ' + res + ' m' : ''}`)
    } catch {
      setStatus('Could not read imagery date (Esri metadata unavailable here).')
    }
  }

  async function exclude(bid: string) {
    setStatus('Removing building…')
    try {
      await api.excludeBuilding(projectId, bid, 'not serviceable')
      setStatus('Building removed (reversible — kept in audit).')
      onChanged()
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not remove.')
    }
  }

  function undo() {
    verts.current.pop()
    drawData()
  }

  async function finish() {
    if (modeRef.current === 'corridor') { await finishCorridor(); return }
    if (verts.current.length < 3) { cancel(); return }
    const ring = [...verts.current, verts.current[0]]
    setStatus('Saving building…')
    try {
      const r = await api.createBuilding(projectId,
        { type: 'Polygon', coordinates: [ring] }, source)
      setStatus(`Added ${r.area_sqm.toFixed(0)} m²` +
        (r.commercial_ready ? '' : ' — tagged pilot-only (traced from imagery)'))
      onChanged()
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not save.')
    }
    verts.current = []
    drawData()
  }

  async function finishCorridor() {
    if (verts.current.length < 2) { cancel(); return }
    setStatus('Saving corridor…')
    try {
      const r = await api.createCorridor(projectId,
        { type: 'LineString', coordinates: [...verts.current] },
        corridorType, source)
      setStatus(`Added ${r.length_m.toFixed(0)} m ${r.corridor_type}` +
        (r.commercial_ready ? '' : ' — pilot-only (traced from imagery)') +
        '. Re-run design to route drops along it.')
      onChanged()
    } catch (e) {
      setStatus(e instanceof Error ? e.message : 'Could not save.')
    }
    verts.current = []
    drawData()
  }

  function cancel() {
    verts.current = []
    drawData()
    setStatus(null)
  }

  return (
    <div>
      <div className="grid grid-cols-2 gap-1">
        {([['draw', 'Draw rooftop'], ['corridor', 'Draw corridor'],
           ['exclude', 'Remove building'], ['move', 'Move FDH/FAT'],
           ['inspect', 'Imagery date']] as const)
          .map(([v, label]) => (
          <button key={v}
            className={`rounded px-1.5 py-1 text-[10px] ${
              mode === v ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
            onClick={() => { setMode(mode === v ? 'none' : v as Mode); cancel() }}>
            {label}
          </button>
        ))}
      </div>

      {mode === 'draw' && (
        <>
          <p className="mt-1 text-[10px] text-steel">
            Turn Satellite on, then <b>click each corner</b> of the rooftop.
            Use the buttons below to finish, undo or cancel.
          </p>
          <select className="field mt-1 py-1 text-[10px]" value={source}
                  onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <div className="mt-1 flex items-center justify-between">
            <span className="font-mono text-[10px] text-navy">
              {vertCount} point{vertCount === 1 ? '' : 's'}
              {vertCount > 0 && vertCount < 3
                ? ` · need ${3 - vertCount} more` : ''}
            </span>
            <button className="font-mono text-[10px] text-brand disabled:opacity-40"
                    disabled={vertCount === 0} onClick={undo}>undo</button>
          </div>
          <div className="mt-1 flex gap-1">
            <button className="btn-primary flex-1 py-1 text-[10px] disabled:opacity-40"
                    disabled={vertCount < 3} onClick={() => void finish()}>
              Finish & save
            </button>
            <button className="btn-ghost py-1 text-[10px]" onClick={cancel}>
              Cancel
            </button>
          </div>
        </>
      )}
      {mode === 'corridor' && (
        <>
          <p className="mt-1 text-[10px] text-steel">
            Turn Satellite on, then <b>click along</b> the footpath, pathway or
            fence a drop can follow. Two points minimum. Drops re-route along it
            after the next design run.
          </p>
          <div className="mt-1 flex gap-1">
            <select className="field flex-1 py-1 text-[10px]" value={corridorType}
                    onChange={(e) => setCorridorType(e.target.value)}>
              {CORRIDOR_TYPES.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>))}
            </select>
            <select className="field flex-1 py-1 text-[10px]" value={source}
                    onChange={(e) => setSource(e.target.value)}>
              {SOURCES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
          <div className="mt-1 flex items-center justify-between">
            <span className="font-mono text-[10px] text-navy">
              {vertCount} point{vertCount === 1 ? '' : 's'}
              {vertCount === 1 ? ' · need 1 more' : ''}
            </span>
            <button className="font-mono text-[10px] text-brand disabled:opacity-40"
                    disabled={vertCount === 0} onClick={undo}>undo</button>
          </div>
          <div className="mt-1 flex gap-1">
            <button className="btn-primary flex-1 py-1 text-[10px] disabled:opacity-40"
                    disabled={vertCount < 2} onClick={() => void finish()}>
              Finish & save
            </button>
            <button className="btn-ghost py-1 text-[10px]" onClick={cancel}>
              Cancel
            </button>
          </div>
        </>
      )}
      {mode === 'move' && (
        <p className="mt-1 text-[10px] text-steel">
          Drag an FDH or FAT marker to reposition it. Routes update on refresh.
        </p>
      )}
      {mode === 'exclude' && (
        <p className="mt-1 text-[10px] text-steel">
          Click a building to remove it (non-serviceable). Reversible — the
          record is kept for audit and dropped from map, register and design.
        </p>
      )}
      {mode === 'inspect' && (
        <p className="mt-1 text-[10px] text-steel">
          Click the map to read the Esri imagery capture date there.
        </p>
      )}
      {status && (
        <p className="mt-1 border-t border-lightgrey pt-1 text-[10px] text-navy">
          {status}
        </p>
      )}
    </div>
  )
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
