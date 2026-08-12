import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import maplibregl, { type StyleSpecification } from 'maplibre-gl'
import { api, type Boundary, type Design, type LicenceSummary, type Project, type Street }
  from '../api/client'
import { useAuth } from '../auth/AuthContext'
import AssignmentPanel from '../components/AssignmentPanel'
import CurrencyPanel from '../components/CurrencyPanel'
import DeploymentPanel from '../components/DeploymentPanel'
import DesignPanel from '../components/DesignPanel'
import ManholePanel from '../components/ManholePanel'
import ReportsPanel from '../components/ReportsPanel'
import EditToolbar from '../components/EditToolbar'
import ScenarioPanel from '../components/ScenarioPanel'
import EstatePanel from '../components/EstatePanel'
import ReadinessBanner from '../components/ReadinessBanner'
import StaleDesignBanner from '../components/StaleDesignBanner'
import CleanupPanel from '../components/CleanupPanel'
import ParcelPanel from '../components/ParcelPanel'
import ImportPanel from '../components/ImportPanel'
import LayerControl, { DEFAULT_VISIBILITY, LAYER_GROUPS }
  from '../components/LayerControl'
import StreetPanel from '../components/StreetPanel'
import PremisesModelPanel from '../components/PremisesModelPanel'
import { AccordionRail, AccordionSection } from '../components/Accordion'
import Tabs from '../components/Tabs'
import InspectorDrawer, { type InspectorData } from '../components/InspectorDrawer'
import StatusStrip from '../components/StatusStrip'

/**
 * Default is a plain engineering basemap (SRD FR-GIS-003). A licensed vector
 * style may be supplied via VITE_BASEMAP_STYLE_URL. Proprietary tiles must not
 * be scraped or cached (FR-GIS-016).
 */
const STYLE_URL = import.meta.env.VITE_BASEMAP_STYLE_URL as string | undefined


/**
 * Glyphs are served from the app's own /public/fonts, generated with fontnik.
 * MapLibre requires PBF glyph ranges for any symbol layer and fails silently
 * without them — no error, no text. Self-hosting removes the dependency on an
 * external glyph server entirely, which a deployable product needs anyway.
 * VITE_GLYPHS_URL overrides the location if you move them behind a CDN.
 */
const GLYPHS = (import.meta.env.VITE_GLYPHS_URL as string | undefined)
  ?? '/fonts/{fontstack}/{range}.pbf'

// Must match both the directory under /public/fonts AND the name recorded
// inside the PBF. A stack of several names would make MapLibre request a
// comma-joined fontstack that a static server cannot composite.
const FONT_STACK = ['Liberation Sans Regular']

const PLAIN_STYLE: StyleSpecification = {
  version: 8, glyphs: GLYPHS, sources: {},
  layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#F2F6FB' } }],
}

const WUYE_CENTRE: [number, number] = [7.441, 9.049]

export default function ProjectMap() {
  const { id = '' } = useParams()
  const { can } = useAuth()
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const ready = useRef(false)
  const fittedBoundary = useRef(false)

  const [project, setProject] = useState<Project | null>(null)
  const [boundary, setBoundary] = useState<Boundary | null>(null)
  const [streets, setStreets] = useState<Street[]>([])
  const [licence, setLicence] = useState<LicenceSummary | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [cursor, setCursor] = useState<[number, number]>(WUYE_CENTRE)
  const [selectedStreet, setSelectedStreet] = useState<string | null>(null)
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [selectedParcel, setSelectedParcel] = useState<string | null>(null)
  const [visibility, setVisibility] = useState<Record<string, boolean>>(
    { ...DEFAULT_VISIBILITY })
  const [routePhase, setRoutePhase] = useState<0 | 1 | 2 | 3>(0)
  const [routeMsg, setRouteMsg] = useState<string | null>(null)
  const [mapReady, setMapReady] = useState(false)
  const editMoveRef = useRef(false)
  const [readinessKey, setReadinessKey] = useState(0)
  const [mapError, setMapError] = useState<string | null>(null)
  // Which rail sections are expanded. Starts empty; a one-time effect below
  // computes the default (Project vs Design) once the first load resolves,
  // so a first-time project always opens on Project and a returning one
  // opens on Design — computed, not a stored preference.
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())
  const defaultedOpen = useRef(false)
  const [designTab, setDesignTab] = useState<'layer' | 'edit' | 'review'>('layer')
  const [inspector, setInspector] = useState<InspectorData | null>(null)
  const [zoom, setZoom] = useState(13)
  const [currentDesign, setCurrentDesign] = useState<Design | null>(null)
  const [schemaWarning, setSchemaWarning] = useState<string | null>(null)
  const [labelCount, setLabelCount] = useState<number | null>(null)
  const [sourceCounts, setSourceCounts] = useState<{b: number; s: number; d: number} | null>(null)
  const [fetchErrors, setFetchErrors] = useState<Record<string, string | null>>({})
  const [dropStats, setDropStats] = useState<
    { drop_limit_m: number | null; served: number; unserved: number;
      over_limit: number; routed: number; straight: number } | null>(null)
  const [ringStats, setRingStats] = useState<
    { fdhs_on_ring: number; ring_trench_m: number; tree_feeder_m: number;
      incremental_trench_m: number; ring_cable_m: number;
      unreachable_fdhs: string[] } | null>(null)

  const loadMeta = useCallback(() => {
    setReadinessKey((k) => k + 1)
    api.getProject(id).then(setProject).catch((e) => setError(e.message))
    api.getBoundary(id).then(setBoundary).catch(() => setBoundary(null))
    api.listStreets(id).then(setStreets).catch(() => setStreets([]))
    api.licenceSummary(id).then(setLicence).catch(() => setLicence(null))
  }, [id])

  useEffect(() => { loadMeta() }, [loadMeta])

  // Computed default: open Design once a design run exists (sourceCounts.d
  // > 0), otherwise open Project. Runs once, the first time sourceCounts
  // resolves — after that the user's own clicks are what drive openSections.
  useEffect(() => {
    if (defaultedOpen.current || !sourceCounts) return
    defaultedOpen.current = true
    setOpenSections(new Set([sourceCounts.d > 0 ? 'design' : 'project']))
  }, [sourceCounts])

  const toggleSection = (id: string) => setOpenSections((prev) => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    const src = m.getSource('routes') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    if (routePhase === 0) { src.setData(EMPTY); setRouteMsg(null); return }
    const label = routePhase === 3 ? 'Full network' : `Phase ${routePhase}`
    setRouteMsg('Loading routes…')
    ;(routePhase === 3 ? api.routesFullGeoJSON(id) : api.routesGeoJSON(id, routePhase))
      .then((fc) => {
        src.setData(fc as GeoJSON.FeatureCollection)
        const lineFeats = fc.features.filter(
          (f) => f.geometry?.type === 'LineString')
        if (!lineFeats.length) {
          setRouteMsg(`${label} has no routed geometry yet — ` +
            're-run the design in Pilot mode.')
          return
        }
        // Fit to the drawn phase so the user sees it immediately.
        const pts: number[][] = []
        const walk = (c: unknown): void => {
          if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[])
          else if (Array.isArray(c)) c.forEach(walk)
        }
        fc.features.forEach((f) => walk((f.geometry as GeoJSON.LineString).coordinates))
        if (pts.length) {
          const b = pts.reduce((acc, p) => acc.extend([p[0], p[1]]),
            new maplibregl.LngLatBounds([pts[0][0], pts[0][1]], [pts[0][0], pts[0][1]]))
          m.fitBounds(b, { padding: 80, duration: 600, maxZoom: 17 })
        }
        setRouteMsg(`${label}: ${lineFeats.length} route segments`)
      })
      .catch((e) => { src.setData(EMPTY)
        setRouteMsg(e instanceof Error ? e.message : 'Could not load routes.') })
  }, [routePhase, id])

  useEffect(() => {
    api.ready().then((r) => {
      setSchemaWarning(r.pending_migrations.length ? (r.action ?? null) : null)
    }).catch(() => {})
  }, [])

  // Snapshot of exactly what's on screen right now — whatever the user has
  // zoomed/panned to and whichever layers (e.g. satellite) are toggled on —
  // for the Word report's aerial view. Returns null before the map has
  // rendered a first frame.
  const captureAerial = useCallback((): string | null => {
    const m = map.current
    if (!m) return null
    try {
      return m.getCanvas().toDataURL('image/png')
    } catch {
      return null
    }
  }, [])

  // --- map init ---
  useEffect(() => {
    if (!container.current || map.current) return
    const m = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL || PLAIN_STYLE,
      center: WUYE_CENTRE, zoom: 13,
      attributionControl: { compact: true },
      // Needed for captureAerial() below — without this the WebGL drawing
      // buffer is cleared right after each render and getCanvas().toDataURL()
      // reads back a blank/black image instead of what's on screen.
      preserveDrawingBuffer: true,
    })
    map.current = m
    // MapLibre reports missing glyphs, bad expressions and failed tile loads
    // through this event and nowhere else. Without it they are invisible.
    m.on('error', (e) => {
      const message = (e as unknown as { error?: Error }).error?.message
        ?? 'unknown map error'
      setMapError(message)
      // eslint-disable-next-line no-console
      console.error('[maplibre]', message, e)
    })
    m.addControl(new maplibregl.NavigationControl(), 'top-right')
    m.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left')
    m.on('mousemove', (e) => setCursor([e.lngLat.lng, e.lngLat.lat]))
    m.on('zoom', () => setZoom(m.getZoom()))
    m.on('load', () => {
      ready.current = true
      setMapReady(true)
      setZoom(m.getZoom())
      for (const src of ['boundary', 'buildings', 'streets', 'design', 'parcels', 'routes', 'drops', 'corridors', 'detect-preview', 'noc', 'ring', 'areas', 'manholes', 'building_photos']) {
        m.addSource(src, { type: 'geojson', data: EMPTY })
      }
      // Fault-isolate every layer add. Before this, one bad addLayer threw and
      // silently aborted the whole load handler, so only the layers added
      // before it (boundary) rendered. Now a failure is logged and skipped,
      // and the map still shows everything else.
      const failedLayers: string[] = []
      const addLayer = (spec: maplibregl.LayerSpecification, before?: string) => {
        try { m.addLayer(spec, before) }
        catch (e) {
          failedLayers.push(spec.id)
          // eslint-disable-next-line no-console
          console.error('[maplibre layer]', spec.id, e)
        }
      }
      // Esri World Imagery — free, ~0.5 m over Abuja. Display only: tiles are
      // fetched live and never cached or redistributed (SRD FR-GIS-016).
      m.addSource('satellite', {
        type: 'raster', tileSize: 256, maxzoom: 19,
        tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/' +
                'World_Imagery/MapServer/tile/{z}/{y}/{x}'],
        attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
      })
      addLayer({ id: 'satellite', type: 'raster', source: 'satellite',
        layout: { visibility: 'none' } })   // off by default; toggle in Layers
      addLayer({ id: 'boundary-fill', type: 'fill', source: 'boundary',
        paint: { 'fill-color': '#2589C8', 'fill-opacity': 0.06 } })
      addLayer({ id: 'boundary-line', type: 'line', source: 'boundary',
        paint: { 'line-color': '#0D1B4B', 'line-width': 2, 'line-dasharray': [3, 2] } })
      // Parcels sit under the buildings: the property boundary is context,
      // the buildings are the subject.
      addLayer({ id: 'parcel-fill', type: 'fill', source: 'parcels',
        paint: {
          'fill-color': ['case', ['get', 'has_units'], '#00C9A7', '#8FA3BF'],
          'fill-opacity': 0.10,
        } })
      addLayer({ id: 'parcel-selected', type: 'line', source: 'parcels',
        filter: ['==', ['get', 'parcel_id'], '__none__'],
        paint: { 'line-color': '#00C9A7', 'line-width': 4 } })
      m.on('click', 'parcel-fill', (e) => {
        const f = e.features?.[0]
        if (f?.properties?.parcel_id) setSelectedParcel(String(f.properties.parcel_id))
      })
      addLayer({ id: 'parcel-line', type: 'line', source: 'parcels',
        paint: {
          'line-color': ['case', ['get', 'has_units'], '#00C9A7', '#5A739A'],
          'line-width': 1.5,
        } })
      // Estate names are the primary orientation label on a busy map, so they
      // are larger and warmer than street names and appear earlier.
      addLayer({ id: 'parcel-label', type: 'symbol', source: 'parcels',
        minzoom: 13,
        layout: {
          'text-field': ['get', 'name'],
          'text-font': FONT_STACK,
          // Grow with zoom, and give larger estates larger labels so the map
          // reads by importance rather than uniformly.
          'text-size': ['interpolate', ['linear'], ['zoom'],
            13, ['case', ['>', ['get', 'area_sqm'], 8000], 13, 11],
            16, ['case', ['>', ['get', 'area_sqm'], 8000], 18, 15],
            18, 20],
          'text-max-width': 10,
          'text-allow-overlap': false,
          'text-padding': 4,
        },
        paint: {
          // Amber against a blue-grey map: unmistakably an estate, and
          // distinct from the teal used for confirmed streets and FATs.
          'text-color': ['case', ['get', 'has_units'], '#B45309', '#8A5A00'],
          'text-halo-color': '#ffffff',
          'text-halo-width': 2.5,
          'text-halo-blur': 0.5,
        } })
      addLayer({ id: 'buildings-fill', type: 'fill', source: 'buildings',
        paint: {
          // Colour by licence class so the commercial position is visible on
          // the map, not buried in a report.
          // Served buildings (assigned to a FAT) read teal; unserved stay
          // grey, so FAT coverage is visible without opening the schedule.
          'fill-color': ['case',
            ['has', 'serving_fat'], '#00C9A7',
            ['match', ['get', 'currency'],
              'current', '#4BAADF', 'ageing', '#4BAADF',
              'stale', '#8FA3BF', 'obsolete', '#8FA3BF', '#8FA3BF']],
          'fill-opacity': ['case', ['has', 'serving_fat'], 0.8, 0.5],
        } })
      addLayer({ id: 'buildings-label', type: 'symbol', source: 'buildings',
        minzoom: 17.5,
        filter: ['has', 'code'],
        layout: {
          // The suffix (B03) is enough at building scale; the full code is in
          // the popup and the schedule.
          'text-field': ['slice', ['get', 'code'], ['-',
            ['length', ['get', 'code']], 3]],
          'text-font': FONT_STACK, 'text-size': 10,
        },
        paint: { 'text-color': '#0D1B4B', 'text-halo-color': '#fff',
                 'text-halo-width': 1.5 } })
      addLayer({ id: 'buildings-line', type: 'line', source: 'buildings',
        minzoom: 12,
        paint: {
          'line-color': '#0D1B4B',
          'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 1.2],
          'line-opacity': 0.85,
        } })
      // Named roads read as confirmed; unnamed ones as outstanding work.
      addLayer({ id: 'streets-line', type: 'line', source: 'streets',
        paint: {
          'line-color': ['match', ['get', 'name_state'],
            'confirmed', '#00C9A7',    // field verified
            'identified', '#2589C8',   // imported name, unverified
            '#8FA3BF'],                // unnamed
          'line-width': ['match', ['get', 'name_state'],
            'confirmed', 3.5, 'identified', 2.5, 1.5],
        } })
      addLayer({ id: 'streets-label', type: 'symbol', source: 'streets',
        // Well below the zoom the district fits at. Gating labels at the
        // opening zoom made them vanish the moment fitBounds ran.
        minzoom: 10.5,
        filter: ['get', 'named'],
        layout: {
          'symbol-placement': 'line', 'text-field': ['get', 'name'],
          'text-font': FONT_STACK,
          'text-size': 12, 'text-max-angle': 40, 'symbol-spacing': 300,
          'text-allow-overlap': false, 'text-ignore-placement': false,
        },
        paint: {
          // Confirmed names read solid; unverified ones deliberately lighter.
          'text-color': ['match', ['get', 'name_state'],
            'confirmed', '#0D1B4B', '#5A739A'],
          'text-halo-color': '#ffffff', 'text-halo-width': 2,
        } })
      // Provisional codes appear only when zoomed in, so they do not compete
      // with real names at district scale.
      // Provisional codes are the thing being read off the map and typed into
      // the panel, so they are legible at working zoom, not only close in.
      addLayer({ id: 'streets-code', type: 'symbol', source: 'streets',
        minzoom: 12,
        filter: ['!', ['get', 'named']],
        layout: {
          'symbol-placement': 'line', 'text-field': ['get', 'code'],
          'text-font': FONT_STACK,
          'text-size': 11, 'text-max-angle': 40, 'symbol-spacing': 260,
        },
        paint: { 'text-color': '#1A2E72', 'text-halo-color': '#ffffff',
                 'text-halo-width': 2 } })
      // Highlight for whichever street is being renamed.
      addLayer({ id: 'streets-selected', type: 'line', source: 'streets',
        filter: ['==', ['get', 'code'], '__none__'],
        paint: { 'line-color': '#00C9A7', 'line-width': 9,
                 'line-opacity': 0.45, 'line-blur': 1 } }, 'streets-line')
      m.on('click', 'streets-line', (e) => {
        const f = e.features?.[0]
        if (!f) return
        if (f.properties?.street_id) setSelectedStreet(String(f.properties.street_id))
        setInspector({
          title: String(f.properties?.label ?? 'Street'),
          subtitle: String(f.properties?.code ?? ''),
          rows: [
            { label: 'Road class', value: String(f.properties?.road_class ?? '—') },
            { label: 'Length', value: `${Number(f.properties?.length_m).toFixed(0)} m` },
            { label: 'Naming', value: f.properties?.named
                ? 'named — ' + (f.properties?.name_source ?? 'source unrecorded')
                : 'awaiting a field name' },
          ],
          media: f.properties?.street_id
            ? { projectId: id, entityType: 'street', entityId: String(f.properties.street_id) }
            : undefined,
        })
      })
      m.on('mouseenter', 'streets-line', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'streets-line', () => { m.getCanvas().style.cursor = '' })
      // --- design layers ---
      addLayer({ id: 'zone-extent', type: 'fill', source: 'design',
        filter: ['==', ['get', 'kind'], 'extent'],
        paint: {
          // Utilisation is the thing a designer reads off a zone map.
          'fill-color': ['interpolate', ['linear'], ['get', 'utilisation'],
            0, '#E8EEF6', 50, '#A8D4EE', 85, '#2589C8', 100, '#0D1B4B'],
          'fill-opacity': 0.35,
        } })
      addLayer({ id: 'zone-outline', type: 'line', source: 'design',
        filter: ['==', ['get', 'kind'], 'extent'],
        paint: { 'line-color': '#1A6FA8', 'line-width': 1, 'line-opacity': 0.6 } })
      addLayer({ id: 'zone-selected', type: 'line', source: 'design',
        filter: ['all', ['==', ['get', 'kind'], 'extent'],
                 ['==', ['get', 'zone_code'], '__none__']],
        paint: { 'line-color': '#00C9A7', 'line-width': 4 } })
      addLayer({ id: 'fat-point', type: 'circle', source: 'design',
        filter: ['==', ['get', 'kind'], 'fat'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 3, 17, 8],
          'circle-color': ['case', ['get', 'has_warning'], '#1A6FA8', '#00C9A7'],
          'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff',
        } })
      // Traced drop corridors (footpaths, fences, service ways).
      addLayer({ id: 'corridor-line', type: 'line', source: 'corridors',
        paint: {
          'line-color': '#7A5CF0',   // violet, distinct from streets/routes
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 1, 18, 3],
          'line-opacity': 0.9, 'line-dasharray': [1, 1],
        } })
      // Detected-footprint preview (magenta) — shown before committing an import.
      addLayer({ id: 'detect-preview-fill', type: 'fill', source: 'detect-preview',
        paint: { 'fill-color': '#E5189D', 'fill-opacity': 0.25 } })
      addLayer({ id: 'detect-preview-line', type: 'line', source: 'detect-preview',
        paint: { 'line-color': '#E5189D', 'line-width': 1.2, 'line-opacity': 0.9 } })
      // Per-building drop routes: FAT -> premises, coloured by serviceability.
      // White casing + full opacity so drops read over teal building fills.
      addLayer({ id: 'drop-case', type: 'line', source: 'drops',
        filter: ['==', ['get', 'kind'], 'drop'],
        paint: {
          'line-color': '#ffffff',
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 2.4, 18, 6],
          'line-opacity': 0.85,
        } })
      addLayer({ id: 'drop-line', type: 'line', source: 'drops',
        filter: ['==', ['get', 'kind'], 'drop'],
        paint: {
          'line-color': ['case', ['get', 'serviceable'], '#00893D', '#E5484D'],
          'line-width': ['interpolate', ['linear'], ['zoom'], 13, 1.3, 18, 3.2],
          'line-opacity': 1, 'line-dasharray': [2, 1.2],
        } })
      addLayer({ id: 'drop-unserved', type: 'circle', source: 'drops',
        filter: ['==', ['get', 'kind'], 'unserved'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 2.5, 18, 6],
          'circle-color': '#E5484D', 'circle-opacity': 0.85,
          'circle-stroke-width': 1, 'circle-stroke-color': '#ffffff',
        } })
      // White casing under each route so it reads over buildings and roads.
      addLayer({ id: 'route-distribution-case', type: 'line', source: 'routes',
        filter: ['==', ['get', 'kind'], 'distribution'],
        paint: { 'line-color': '#ffffff', 'line-width': 6, 'line-opacity': 0.9 } })
      addLayer({ id: 'route-distribution', type: 'line', source: 'routes',
        filter: ['==', ['get', 'kind'], 'distribution'],
        paint: { 'line-color': '#0066FF', 'line-width': 3.5 } })   // electric blue
      addLayer({ id: 'route-feeder-case', type: 'line', source: 'routes',
        filter: ['==', ['get', 'kind'], 'feeder'],
        paint: { 'line-color': '#ffffff', 'line-width': 8, 'line-opacity': 0.9 } })
      addLayer({ id: 'route-feeder', type: 'line', source: 'routes',
        filter: ['==', ['get', 'kind'], 'feeder'],
        paint: { 'line-color': '#FF6A00', 'line-width': 5 } })     // orange
      addLayer({ id: 'route-noc', type: 'circle', source: 'routes',
        filter: ['==', ['get', 'kind'], 'noc'],
        paint: { 'circle-radius': 9, 'circle-color': '#0D1B4B',
                 'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' } })
      addLayer({ id: 'route-noc-label', type: 'symbol', source: 'routes',
        filter: ['==', ['get', 'kind'], 'noc'],
        layout: { 'text-field': 'NOC', 'text-font': FONT_STACK, 'text-size': 12,
                  'text-offset': [0, 1.4], 'text-anchor': 'top' },
        paint: { 'text-color': '#0D1B4B', 'text-halo-color': '#fff',
                 'text-halo-width': 2 } })
      addLayer({ id: 'fdh-point', type: 'circle', source: 'design',
        filter: ['==', ['get', 'kind'], 'fdh'],
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 6, 17, 14],
          'circle-color': '#B45309',
          'circle-stroke-width': 2.5, 'circle-stroke-color': '#ffffff',
        } })
      addLayer({ id: 'fdh-label', type: 'symbol', source: 'design',
        minzoom: 13,
        filter: ['==', ['get', 'kind'], 'fdh'],
        layout: { 'text-field': ['get', 'code'], 'text-font': FONT_STACK,
                  'text-size': 12, 'text-offset': [0, 1.3], 'text-anchor': 'top' },
        paint: { 'text-color': '#7C3A00', 'text-halo-color': '#ffffff',
                 'text-halo-width': 2 } })
      m.on('click', 'fdh-point', (e) => {
        const f = e.features?.[0]
        if (!f) return
        setInspector({
          title: String(f.properties?.code ?? 'FDH'),
          subtitle: `${f.properties?.splitters} × 1:32 splitters`,
          rows: [
            { label: 'Premises', value: `${f.properties?.premises}/${f.properties?.capacity}` },
            { label: 'FATs', value: String(f.properties?.fats ?? '—') },
            { label: 'Utilisation', value: `${Number(f.properties?.utilisation).toFixed(0)}%` },
            { label: 'Reach', value: `${Number(f.properties?.reach_m).toFixed(0)} m` },
          ],
        })
      })
      m.on('mouseenter', 'fdh-point', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'fdh-point', () => { m.getCanvas().style.cursor = '' })
      // Drag FDH / FAT markers to reposition. In move mode only.
      let dragId: string | null = null
      let dragKind: 'fat' | 'fdh' | null = null
      const startDrag = (layer: string, kind: 'fat' | 'fdh',
                         idProp: string) => {
        m.on('mousedown', layer, (e) => {
          if (!editMoveRef.current) return
          e.preventDefault()
          dragId = String(e.features?.[0]?.properties?.[idProp] ?? '')
          dragKind = kind
          m.dragPan.disable()
          m.getCanvas().style.cursor = 'grabbing'
        })
      }
      startDrag('fat-point', 'fat', 'zone_id')
      startDrag('fdh-point', 'fdh', 'fdh_id')
      m.on('mouseup', async (e) => {
        if (!dragId || !dragKind) return
        const id_ = dragId, kind_ = dragKind
        dragId = null; dragKind = null
        m.dragPan.enable(); m.getCanvas().style.cursor = ''
        try {
          if (kind_ === 'fat') await api.moveFat(id, id_, e.lngLat.lng, e.lngLat.lat)
          else await api.moveFdh(id, id_, e.lngLat.lng, e.lngLat.lat)
          void refreshLayers()
          if (routePhase !== 0) {
            const src = m.getSource('routes') as maplibregl.GeoJSONSource | undefined
            if (src) (routePhase === 3 ? api.routesFullGeoJSON(id) : api.routesGeoJSON(id, routePhase))
              .then((fc) => src.setData(fc as GeoJSON.FeatureCollection)).catch(() => {})
          }
        } catch { /* ignore */ }
      })
      addLayer({ id: 'fat-label', type: 'symbol', source: 'design',
        minzoom: 14.5,
        filter: ['==', ['get', 'kind'], 'fat'],
        layout: { 'text-field': ['get', 'zone_code'], 'text-font': FONT_STACK,
                  'text-size': 10, 'text-offset': [0, 1.1], 'text-anchor': 'top' },
        paint: { 'text-color': '#0D1B4B', 'text-halo-color': '#ffffff',
                 'text-halo-width': 1.5 } })
      // N/S/E/W design areas — orientation guides for per-area exports.
      addLayer({ id: 'area-line', type: 'line', source: 'areas',
        paint: { 'line-color': '#1A2E72', 'line-width': 1.5,
                 'line-dasharray': [4, 3], 'line-opacity': 0.7 } })
      addLayer({ id: 'area-label', type: 'symbol', source: 'areas',
        layout: { 'text-field': ['concat', ['get', 'label'], '\n',
                    ['to-string', ['get', 'fats']], ' FATs · ',
                    ['to-string', ['get', 'premises']], ' prem'],
                  'text-font': FONT_STACK, 'text-size': 13,
                  'text-allow-overlap': true },
        paint: { 'text-color': '#1A2E72', 'text-halo-color': '#ffffff',
                 'text-halo-width': 2 } })
      // Feeder-ring resilience option: closed loop NOC -> FDHs -> NOC.
      addLayer({ id: 'ring-case', type: 'line', source: 'ring',
        paint: { 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 } })
      addLayer({ id: 'ring-line', type: 'line', source: 'ring',
        paint: { 'line-color': '#C2185B', 'line-width': 3.5,
                 'line-dasharray': [3, 1.5] } })
      // The NOC is permanent — every feeder starts and ends here, so it must
      // be visible whether or not the routed design is displayed.
      addLayer({ id: 'noc-halo', type: 'circle', source: 'noc',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 10, 17, 18],
                 'circle-color': '#FF6A00', 'circle-opacity': 0.25 } })
      addLayer({ id: 'noc-point', type: 'circle', source: 'noc',
        paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 6, 17, 11],
                 'circle-color': '#0D1B4B',
                 'circle-stroke-width': 3, 'circle-stroke-color': '#ffffff' } })
      addLayer({ id: 'noc-label', type: 'symbol', source: 'noc',
        layout: { 'text-field': ['get', 'name'], 'text-font': FONT_STACK,
                  'text-size': 12, 'text-offset': [0, 1.6], 'text-anchor': 'top',
                  'text-allow-overlap': true },
        paint: { 'text-color': '#0D1B4B', 'text-halo-color': '#ffffff',
                 'text-halo-width': 2 } })
      m.on('click', 'fat-point', (e) => {
        const f = e.features?.[0]
        if (!f) return
        setSelectedZone(String(f.properties?.zone_code))
        setInspector({
          title: String(f.properties?.zone_code ?? 'FAT'),
          subtitle: `${f.properties?.premises} premises · ${f.properties?.buildings} buildings`,
          rows: [
            { label: 'Utilisation', value: `${Number(f.properties?.utilisation).toFixed(0)}%` },
            { label: 'Spare ports', value: String(f.properties?.spare_ports ?? '—') },
            { label: 'Max drop', value: `${Number(f.properties?.max_drop_m).toFixed(0)} m` },
          ],
          note: f.properties?.premises_assumed
            ? 'Premises assumed, not surveyed.' : undefined,
        })
      })
      m.on('mouseenter', 'fat-point', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'fat-point', () => { m.getCanvas().style.cursor = '' })

      m.on('click', 'buildings-fill', (e) => {
        const f = e.features?.[0]
        if (!f) return
        setInspector({
          title: String(f.properties?.code ?? 'Unnumbered'),
          subtitle: f.properties?.serving_fat
            ? `served by ${f.properties.serving_fat}` : undefined,
          rows: [
            { label: 'Area', value: `${Number(f.properties?.area).toFixed(0)} m²` },
            { label: 'Dataset', value: String(f.properties?.dataset ?? '—') },
            { label: 'Source age', value: `${f.properties?.source_age_years ?? '?'} yr` },
            { label: 'Currency', value: String(f.properties?.currency ?? '—') },
          ],
          media: f.properties?.building_id
            ? { projectId: id, entityType: 'building', entityId: String(f.properties.building_id) }
            : undefined,
        })
      })
      m.on('mouseenter', 'buildings-fill', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'buildings-fill', () => { m.getCanvas().style.cursor = '' })
      // Field-surveyed chambers — condition read at a glance, photos/video one
      // click away via the inspector's media strip.
      addLayer({ id: 'manhole-point', type: 'circle', source: 'manholes',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 3, 18, 7],
          'circle-color': ['match', ['get', 'condition'],
            'good', '#00C9A7', 'fair', '#4BAADF',
            'poor', '#B45309', 'damaged', '#E5484D',
            'buried', '#8FA3BF', 'inaccessible', '#E5484D',
            '#5A739A'],                                       // unknown
          'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff',
        } })
      m.on('click', 'manhole-point', (e) => {
        const f = e.features?.[0]
        if (!f) return
        const manholeId = String(f.properties?.id ?? '')
        setInspector({
          title: String(f.properties?.code || 'Manhole'),
          subtitle: String(f.properties?.type ?? ''),
          rows: [
            { label: 'Condition', value: String(f.properties?.condition ?? 'unknown') },
            { label: 'Surveyed by', value: String(f.properties?.surveyed_by ?? '—') },
            { label: 'Assessed', value: f.properties?.assessed_at
                ? new Date(String(f.properties.assessed_at)).toLocaleDateString() : '—' },
          ],
          note: f.properties?.notes ? String(f.properties.notes) : undefined,
          media: { projectId: id, entityType: 'manhole', entityId: manholeId },
        })
      })
      m.on('mouseenter', 'manhole-point', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'manhole-point', () => { m.getCanvas().style.cursor = '' })
      // Quick building-photo captures from the mobile app — a distinct warm
      // colour (not the manhole condition palette, and not FAT/FDH's navy)
      // so it reads as "a photo was taken here", one click away via the
      // inspector's media strip, same pattern as manholes/buildings above.
      addLayer({ id: 'building-photo-point', type: 'circle', source: 'building_photos',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 13, 3, 18, 7],
          'circle-color': '#E8590C',
          'circle-stroke-width': 1.5, 'circle-stroke-color': '#ffffff',
        } })
      m.on('click', 'building-photo-point', (e) => {
        const f = e.features?.[0]
        if (!f) return
        const photoId = String(f.properties?.id ?? '')
        setInspector({
          title: 'Building photo',
          subtitle: f.properties?.surveyed_by ? `captured by ${f.properties.surveyed_by}` : undefined,
          rows: f.properties?.updated_at
            ? [{ label: 'Captured', value: new Date(String(f.properties.updated_at)).toLocaleDateString() }]
            : [],
          media: { projectId: id, entityType: 'building_photo', entityId: photoId },
        })
      })
      m.on('mouseenter', 'building-photo-point', () => { m.getCanvas().style.cursor = 'pointer' })
      m.on('mouseleave', 'building-photo-point', () => { m.getCanvas().style.cursor = '' })
      if (failedLayers.length) {
        setMapError(`${failedLayers.length} map layer(s) failed to initialise: ` +
          `${failedLayers.join(', ')}. The rest are shown; check the console.`)
      }
      void refreshLayers()
    })
    return () => { m.remove(); map.current = null; ready.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const refreshLayers = useCallback(async () => {
    const m = map.current
    if (!m || !ready.current) return
    // NOTE: drops.geojson is deliberately NOT fetched here. It routes a drop
    // for every served building (thousands of Dijkstra runs) and can take
    // minutes — awaiting it in this batch blocked every other layer from
    // rendering. It now loads lazily, only when the Drops layer is toggled on
    // (see the drops effect below).
    const [b, s, d, p, co, noc, mh, bp] = await Promise.allSettled([
      api.buildingsGeoJSON(id), api.streetsGeoJSON(id), api.designGeoJSON(id),
      api.parcelsGeoJSON(id), api.corridorsGeoJSON(id), api.nocGeoJSON(id),
      api.manholesGeoJSON(id), api.buildingPhotosGeoJSON(id),
    ])
    if (noc.status === 'fulfilled') setData(m, 'noc', noc.value)
    if (p.status === 'fulfilled') setData(m, 'parcels', p.value)
    if (d.status === 'fulfilled') setData(m, 'design', d.value)
    if (co.status === 'fulfilled') setData(m, 'corridors', co.value)
    if (b.status === 'fulfilled') setData(m, 'buildings', b.value)
    if (mh.status === 'fulfilled') setData(m, 'manholes', mh.value)
    if (bp.status === 'fulfilled') setData(m, 'building_photos', bp.value)
    const reason = (r: PromiseSettledResult<unknown>) =>
      r.status === 'rejected'
        ? (r.reason instanceof Error ? r.reason.message : String(r.reason))
        : null
    setFetchErrors({
      buildings: reason(b), streets: reason(s), design: reason(d),
      parcels: reason(p), corridors: reason(co),
    })
    setSourceCounts({
      b: b.status === 'fulfilled' ? b.value.features.length : -1,
      s: s.status === 'fulfilled' ? s.value.features.length : -1,
      d: d.status === 'fulfilled' ? d.value.features.length : -1,
    })
    if (s.status === 'fulfilled') {
      setData(m, 'streets', s.value)
      const named = s.value.features.filter((f) => f.properties?.named).length
      setLabelCount(named)
    }
  }, [id])

  // Drops load lazily, and only while the Drops layer is on, because routing a
  // drop per building is expensive. Keeping it out of refreshLayers means a
  // slow drops computation can never stall the buildings/streets/design layers.
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !visibility.drops) return
    let cancelled = false
    setDropStats(null)
    api.dropsGeoJSON(id).then((fc) => {
      if (cancelled) return
      setData(m, 'drops', fc)
      setDropStats(fc.properties ?? null)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [visibility.drops, id, mapReady, readinessKey])

  // Design areas load on demand when the layer is switched on.
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !visibility.areas) return
    let cancelled = false
    api.areasGeoJSON(id).then((fc) => {
      if (!cancelled) setData(m, 'areas', fc)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [visibility.areas, id, mapReady, readinessKey])

  // The feeder ring is an option, not the design — computed on demand, only
  // while its layer is on (N+1 Dijkstras + 2-opt, a few seconds).
  useEffect(() => {
    const m = map.current
    if (!m || !mapReady || !visibility.ring) return
    let cancelled = false
    setRingStats(null)
    api.ringGeoJSON(id).then((fc) => {
      if (cancelled) return
      setData(m, 'ring', fc)
      setRingStats(fc.properties ?? null)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [visibility.ring, id, mapReady, readinessKey])

  // boundary → source (+ fit only the first time, so refreshes after an edit
  // never yank the camera away from where the user is working)
  useEffect(() => {
    const m = map.current
    if (!m || !boundary) return
    const apply = () => {
      setData(m, 'boundary', {
        type: 'FeatureCollection',
        features: [{ type: 'Feature', properties: {}, geometry: boundary.geometry }],
      })
      if (!fittedBoundary.current) {
        const b = bounds(boundary.geometry)
        if (b) m.fitBounds(b, { padding: 50, duration: 0 })
        fittedBoundary.current = true
      }
      void refreshLayers()
    }
    if (ready.current) apply()
    else m.once('load', apply)
  }, [boundary, refreshLayers])

  // Highlight the selected street and bring it into view.
  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    const street = streets.find((s) => s.id === selectedStreet)
    if (!m.getLayer('streets-selected')) return
    m.setFilter('streets-selected',
      ['==', ['get', 'code'], street?.street_code ?? '__none__'])
    if (!street) return
    void (async () => {
      const fc = await api.streetsGeoJSON(id)
      const f = fc.features.find((x) => x.properties?.code === street.street_code)
      if (!f) return
      const pts: number[][] = []
      const walk = (c: unknown): void => {
        if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[])
        else if (Array.isArray(c)) c.forEach(walk)
      }
      walk((f.geometry as GeoJSON.LineString).coordinates)
      if (!pts.length) return
      const b = pts.reduce((acc, p) => acc.extend([p[0], p[1]]),
        new maplibregl.LngLatBounds([pts[0][0], pts[0][1]], [pts[0][0], pts[0][1]]))
      m.fitBounds(b, { padding: 140, duration: 400, maxZoom: 17 })
    })()
  }, [selectedStreet, streets, id])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current || !m.getLayer('zone-selected')) return
    m.setFilter('zone-selected', ['all', ['==', ['get', 'kind'], 'extent'],
      ['==', ['get', 'zone_code'], selectedZone ?? '__none__']])
  }, [selectedZone])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current || !m.getLayer('parcel-selected')) return
    m.setFilter('parcel-selected',
      ['==', ['get', 'parcel_id'], selectedParcel ?? '__none__'])
    if (!selectedParcel) return
    void (async () => {
      const fc = await api.parcelsGeoJSON(id)
      const f = fc.features.find((x) => x.properties?.parcel_id === selectedParcel)
      if (!f) return
      const pts: number[][] = []
      const walk = (c: unknown): void => {
        if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[])
        else if (Array.isArray(c)) c.forEach(walk)
      }
      walk((f.geometry as GeoJSON.Polygon).coordinates)
      if (!pts.length) return
      const b = pts.reduce((acc, p) => acc.extend([p[0], p[1]]),
        new maplibregl.LngLatBounds([pts[0][0], pts[0][1]], [pts[0][0], pts[0][1]]))
      m.fitBounds(b, { padding: 120, duration: 400, maxZoom: 18 })
    })()
  }, [selectedParcel, id])

  useEffect(() => {
    const m = map.current
    if (!m || !ready.current) return
    for (const group of LAYER_GROUPS) {
      const on = visibility[group.key] ?? true
      for (const layer of group.layers) {
        if (m.getLayer(layer)) {
          m.setLayoutProperty(layer, 'visibility', on ? 'visible' : 'none')
        }
      }
    }
  }, [visibility])

  async function uploadBoundary(file: File) {
    setError(null); setBusy(true)
    try {
      setBoundary(await api.uploadBoundary(id, file))
      loadMeta()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Boundary upload failed.')
    } finally { setBusy(false) }
  }

  const totalBuildings = licence?.total ?? 0

  return (
    <div className="flex h-full flex-col">
      <div className="flex min-h-0 flex-1">
        <AccordionRail>
          <div className="border-b border-lightgrey p-4">
            <Link to="/projects" className="font-mono text-[11px] uppercase text-brand">
              ← Projects
            </Link>
            <h1 className="mt-2 text-lg text-navy">{project?.name ?? '…'}</h1>
            {project && (
              <p className="text-sm text-steel">
                {[project.district, project.city, project.state].filter(Boolean).join(' · ')}
              </p>
            )}
          </div>

          <AccordionSection id="project" title="Project"
            subtitle={`${totalBuildings.toLocaleString()} buildings · ${streets.length} streets`}
            open={openSections.has('project')} onToggle={toggleSection}>
            <Link to={`/projects/${id}/register`}
                  className="btn-primary mt-1 w-full">Building register →</Link>

            <dl className="mt-4 space-y-2 border-t border-lightgrey pt-3 text-sm">
              <Row label="Code prefix" value={project?.code_prefix} mono />
              <Row label="Storage CRS" value="EPSG:4326" mono />
              <Row label="Metric CRS" value={project ? `EPSG:${project.metric_crs_epsg}` : ''} mono />
              <Row label="Buildings" value={totalBuildings.toLocaleString()} mono />
              <Row label="Streets" value={String(streets.length)} mono />
            </dl>

            <div className="mt-4 border-t border-lightgrey pt-3">
              <h2 className="label">Project boundary</h2>
              {boundary ? (
                <div className="card p-3 text-sm">
                  <p className="text-navy">{boundary.source_filename}</p>
                  <p className="mt-1 font-mono text-xs text-brand">
                    {boundary.area_sqkm.toFixed(3)} km²
                  </p>
                  <span className="badge mt-2 bg-lightgrey text-steel">
                    {boundary.verification_state}
                  </span>
                </div>
              ) : <p className="text-sm text-steel">No boundary uploaded yet.</p>}

              {can('gis:import') && (
                <label className="btn-ghost mt-3 w-full cursor-pointer">
                  {busy ? 'Uploading…' : boundary ? 'Replace boundary' : 'Upload boundary'}
                  <input type="file" className="hidden" accept=".kml,.kmz,.geojson,.json"
                         disabled={busy}
                         onChange={(e) => {
                           const f = e.target.files?.[0]
                           if (f) void uploadBoundary(f)
                           e.target.value = ''
                         }} />
                </label>
              )}
            </div>

            {can('gis:import') && (
              <ImportPanel projectId={id} disabled={!boundary} licence={licence}
                           onImported={() => { loadMeta(); void refreshLayers() }}
                           onPreview={(fc) => { const m = map.current
                             if (m) setData(m, 'detect-preview', fc ?? EMPTY) }} />
            )}

            <CurrencyPanel projectId={id} />

            {totalBuildings > 0 && (
              <div className="mt-3 rounded bg-lightgrey/60 px-2.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
                  Building data age
                </p>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-steel">
                  <span><Swatch c="#00C9A7" /> current</span>
                  <span><Swatch c="#4BAADF" /> ageing</span>
                  <span><Swatch c="#1A6FA8" /> stale</span>
                  <span><Swatch c="#0D1B4B" /> obsolete</span>
                </div>
              </div>
            )}

            {error && (
              <p className="mt-4 rounded border-l-2 border-brand bg-lightgrey px-3 py-2 text-sm">
                {error}
              </p>
            )}
          </AccordionSection>

          <AccordionSection id="survey" title="Survey"
            subtitle={streets.length
              ? `${labelCount ?? 0}/${streets.length} streets named`
              : undefined}
            open={openSections.has('survey')} onToggle={toggleSection}>
            {can('gis:import') && streets.length > 0 && (
              <AssignmentPanel projectId={id}
                               onDone={() => { loadMeta(); void refreshLayers() }} />
            )}

            {can('gis:import') && (
              <ParcelPanel projectId={id}
                           onChanged={() => { loadMeta(); void refreshLayers() }}
                           selectedParcel={selectedParcel}
                           onParcelSelect={setSelectedParcel} />
            )}

            <EstatePanel projectId={id} />

            <PremisesModelPanel projectId={id} />

            <ManholePanel projectId={id} />

            <Link to={`/projects/${id}/street-matching`}
                  className="btn-ghost mt-3 w-full">Match recorded street names →</Link>

            {streets.length > 0 && (
              <StreetPanel
                projectId={id} streets={streets} selectedId={selectedStreet}
                onSelect={setSelectedStreet}
                onChanged={() => { loadMeta(); void refreshLayers() }}
              />
            )}

            {streets.length > 0 && (
              <div className="mt-3 rounded bg-lightgrey/60 px-2.5 py-2">
                <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
                  Street naming
                </p>
                {([
                  ['confirmed', '#00C9A7', 'Confirmed'],
                  ['identified', '#2589C8', 'Identified'],
                  ['unnamed', '#8FA3BF', 'Unnamed'],
                ] as const).map(([key, colour, label]) => {
                  const n = streets.filter((s) => s.name_state === key).length
                  return (
                    <div key={key} className="mt-1 flex items-baseline justify-between">
                      <span className="flex items-center gap-1.5 text-[11px] text-navy">
                        <span className="inline-block h-2 w-2 rounded-sm"
                              style={{ background: colour }} />
                        {label}
                      </span>
                      <span className="font-mono text-[11px] text-navy">{n}</span>
                    </div>
                  )
                })}
                <p className="mt-1 border-t border-lightgrey pt-1 text-[10px] text-steel">
                  Confirmed names are evidenced; identified ones are not.
                </p>
              </div>
            )}
          </AccordionSection>

          <AccordionSection id="design" title="Design"
            subtitle={sourceCounts && sourceCounts.d > 0
              ? `${sourceCounts.d.toLocaleString()} design features` : 'no design run yet'}
            open={openSections.has('design')} onToggle={toggleSection}>
            {can('gis:edit') && totalBuildings > 0 && (
              <DesignPanel projectId={id}
                           onDesignChanged={() => { loadMeta(); void refreshLayers() }}
                           onZoneSelect={setSelectedZone}
                           selectedZone={selectedZone}
                           onDesignLoaded={setCurrentDesign} />
            )}

            {can('gis:edit') && totalBuildings > 0 && (
              <ScenarioPanel projectId={id} />
            )}

            <div className="mt-4 border-t border-lightgrey pt-3">
              <Tabs active={designTab} onChange={(v) => setDesignTab(v as typeof designTab)}
                    tabs={[{ value: 'layer', label: 'Layer' },
                           { value: 'edit', label: 'Edit' },
                           { value: 'review', label: 'Review' }]}>
                {designTab === 'layer' && (
                  <LayerControl visibility={visibility} onChange={setVisibility} />
                )}

                {designTab === 'edit' && can('gis:edit') && (
                  <EditToolbar projectId={id} map={map.current} ready={mapReady}
                               onChanged={() => { loadMeta(); void refreshLayers() }}
                               onMoveMode={(on) => { editMoveRef.current = on }} />
                )}
                {designTab === 'edit' && !can('gis:edit') && (
                  <p className="text-[11px] text-steel">
                    You don't have edit permission on this project.
                  </p>
                )}

                {designTab === 'review' && (
                  <div className="space-y-3">
                    {totalBuildings > 0 && (
                      <div>
                        <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
                          Routed design
                        </p>
                        <div className="mt-1 flex gap-1">
                          {([[0, 'off'], [3, 'Full'], [1, 'Phase 1'], [2, 'Phase 2']] as const).map(([v, label]) => (
                            <button key={v}
                              className={`flex-1 rounded px-1.5 py-1 font-mono text-[10px] uppercase
                                ${routePhase === v ? 'bg-navy text-white' : 'bg-lightgrey text-steel'}`}
                              onClick={() => setRoutePhase(v as 0 | 1 | 2 | 3)}>{label}</button>
                          ))}
                        </div>
                        <div className="mt-1 flex gap-2 text-[10px] text-steel">
                          <span><Swatch c="#FF6A00" /> feeder</span>
                          <span><Swatch c="#0066FF" /> distribution</span>
                        </div>
                        <div className="mt-1 flex flex-col gap-0.5 border-t border-lightgrey pt-1 text-[10px] text-steel">
                          <span><Swatch c="#00C9A7" /> FAT — clean</span>
                          <span><Swatch c="#1A6FA8" /> FAT — needs review (siting / drop length / assumed premises — click for detail)</span>
                          <span><Swatch c="#B45309" /> FDH cabinet</span>
                        </div>
                        {routeMsg && (
                          <p className="mt-1 border-t border-lightgrey pt-1 text-[10px] text-navy">
                            {routeMsg}
                          </p>
                        )}
                      </div>
                    )}
                    {visibility.drops && dropStats && (
                      <div className="border-t border-lightgrey pt-2">
                        <p className="font-mono text-[10px] uppercase tracking-wide text-brand">
                          Drop serviceability
                        </p>
                        <p className="mt-1 text-[11px] text-navy">
                          <span className="text-[#00A36C]">●</span> {dropStats.served} served
                          {dropStats.over_limit > 0 && (
                            <> · <span className="text-[#E5484D]">●</span> {dropStats.over_limit} over {dropStats.drop_limit_m}m</>
                          )}
                          {dropStats.unserved > 0 && (
                            <> · <span className="text-[#E5484D]">◍</span> {dropStats.unserved} unserved</>
                          )}
                        </p>
                        <p className="mt-1 text-[9px] text-steel">
                          Routed along streets/pathways, measured cable. Green ≤ {dropStats.drop_limit_m}m.
                          {dropStats.straight > 0 && ` ${dropStats.straight} fell back to straight line (no corridor).`}
                        </p>
                      </div>
                    )}
                    {visibility.ring && ringStats && (
                      <div className="border-t border-lightgrey pt-2">
                        <p className="font-mono text-[10px] uppercase tracking-wide text-[#C2185B]">
                          Feeder ring (option)
                        </p>
                        <p className="mt-1 text-[11px] text-navy">
                          {ringStats.fdhs_on_ring} FDHs · ring {(ringStats.ring_trench_m / 1000).toFixed(1)} km
                          {' '}vs tree {(ringStats.tree_feeder_m / 1000).toFixed(1)} km
                        </p>
                        <p className="text-[10px] text-steel">
                          increment ≤ {(ringStats.incremental_trench_m / 1000).toFixed(1)} km trench ·
                          ring cable {(ringStats.ring_cable_m / 1000).toFixed(1)} km
                          {ringStats.unreachable_fdhs.length > 0 &&
                            ` · ${ringStats.unreachable_fdhs.length} FDH unreachable`}
                        </p>
                      </div>
                    )}
                    {!(totalBuildings > 0) && !dropStats && !ringStats && (
                      <p className="text-[11px] text-steel">
                        Run a design to see routed phases and serviceability here.
                      </p>
                    )}
                  </div>
                )}
              </Tabs>
            </div>
          </AccordionSection>

          <AccordionSection id="reports" title="Reports"
            subtitle="pack · schematics · areas"
            open={openSections.has('reports')} onToggle={toggleSection}>
            <ReportsPanel projectId={id} hasDesign={!!currentDesign?.design_run_id}
              captureAerial={captureAerial} />
          </AccordionSection>

          <AccordionSection id="deployment" title="Deployment"
            subtitle="tasks · status · issues"
            open={openSections.has('deployment')} onToggle={toggleSection}>
            <DeploymentPanel projectId={id} />
          </AccordionSection>

          <AccordionSection id="admin" title="Admin"
            subtitle="readiness · cleanup"
            open={openSections.has('admin')} onToggle={toggleSection}>
            <ReadinessBanner projectId={id} refreshKey={readinessKey} />
            {can('gis:edit') && (
              <CleanupPanel projectId={id}
                onPreview={(fc) => { const m = map.current; if (m) setData(m, 'detect-preview', fc ?? EMPTY) }}
                onChanged={() => { loadMeta(); void refreshLayers() }} />
            )}
          </AccordionSection>
        </AccordionRail>

        <div className="relative min-w-0 flex-1">
          <div ref={container} className="absolute inset-0" />

          {/* Exceptions stay as loud banners above the map — they need
              attention, unlike the routine counts in the bottom strip. */}
          <div className="pointer-events-none absolute left-2 top-2 z-20 w-72 space-y-2">
            {Object.entries(fetchErrors).some(([, v]) => v) && (
              <div className="pointer-events-auto rounded border-l-2 border-red-600 bg-white px-3 py-2 shadow-lg">
                <p className="font-mono text-[10px] uppercase tracking-wide text-red-600">
                  Map data failed to load
                </p>
                <ul className="mt-1 space-y-0.5">
                  {Object.entries(fetchErrors).filter(([, v]) => v).map(([k, v]) => (
                    <li key={k} className="text-[10px] text-navy">
                      <b>{k}:</b> {v}
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-[9px] text-steel">
                  Boundary uses a different endpoint, so it still shows. Fix the
                  above and reload.
                </p>
              </div>
            )}

            <StaleDesignBanner projectId={id} refreshKey={readinessKey}
                               onRerun={() => { loadMeta(); void refreshLayers() }} />

            {schemaWarning && (
              <div className="pointer-events-auto rounded border-l-2 border-brand bg-white/95 px-2.5 py-2 shadow-sm">
                <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
                  Database schema is behind
                </p>
                <p className="mt-1 text-[10px] text-steel">{schemaWarning}</p>
              </div>
            )}

            {mapError && (
              <div className="pointer-events-auto rounded border-l-2 border-brand bg-white/95 px-2.5 py-2 shadow-sm">
                <p className="font-mono text-[10px] uppercase tracking-wide text-navy">
                  Map error
                </p>
                <p className="mt-1 break-words text-[10px] text-steel">{mapError}</p>
                <button className="mt-1 font-mono text-[10px] text-brand"
                        onClick={() => setMapError(null)}>dismiss</button>
              </div>
            )}

            {!STYLE_URL && (
              <div className="pointer-events-none rounded bg-white/90 px-2 py-1 font-mono text-[10px] text-midgrey">
                PLAIN ENGINEERING BASEMAP — no imagery licence
              </div>
            )}
          </div>

          <InspectorDrawer data={inspector} onClose={() => setInspector(null)} />

          <button
            className="pointer-events-auto absolute bottom-3 right-2 z-10 rounded
                       bg-white px-2 py-1 font-mono text-[10px] uppercase
                       tracking-wide text-brand shadow hover:bg-lightgrey"
            title="Download the current map view as a PNG image"
            onClick={() => {
              const m = map.current
              if (!m) return
              // The GL context is not preserved between frames, so grab the
              // canvas inside a render callback and force one repaint.
              m.once('render', () => {
                m.getCanvas().toBlob((b) => {
                  if (!b) return
                  const a = document.createElement('a')
                  a.href = URL.createObjectURL(b)
                  a.download = 'wuye_design_map.png'
                  a.click()
                  URL.revokeObjectURL(a.href)
                })
              })
              m.triggerRepaint()
            }}>
            Export PNG
          </button>
        </div>
      </div>

      <StatusStrip
        buildings={sourceCounts ? sourceCounts.b : null}
        streets={sourceCounts ? sourceCounts.s : null}
        designFeatures={sourceCounts ? sourceCounts.d : null}
        zoom={zoom} lng={cursor[0]} lat={cursor[1]} />
    </div>
  )
}

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

function setData(m: maplibregl.Map, id: string, data: unknown) {
  const src = m.getSource(id) as maplibregl.GeoJSONSource | undefined
  if (src) src.setData(data as GeoJSON.FeatureCollection)
}

function bounds(geometry: GeoJSON.Geometry): maplibregl.LngLatBounds | null {
  const pts: number[][] = []
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') pts.push(c as number[])
    else if (Array.isArray(c)) c.forEach(walk)
  }
  walk((geometry as GeoJSON.Polygon).coordinates)
  if (!pts.length) return null
  return pts.reduce((b, c) => b.extend([c[0], c[1]]),
    new maplibregl.LngLatBounds([pts[0][0], pts[0][1]], [pts[0][0], pts[0][1]]))
}

function Swatch({ c }: { c: string }) {
  return <span className="mr-1 inline-block h-2 w-2 rounded-sm align-middle"
               style={{ background: c }} />
}

function Row({ label, value, mono }: { label: string; value?: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-steel">{label}</dt>
      <dd className={mono ? 'font-mono text-xs text-navy' : 'text-navy'}>{value ?? '—'}</dd>
    </div>
  )
}
