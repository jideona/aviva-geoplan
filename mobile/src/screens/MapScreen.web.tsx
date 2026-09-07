// Map screen — web build. react-native-maps has no working web target (its
// web shim throws a hard bundling error pulling in native codegen modules —
// confirmed while building this PWA export, not a theoretical concern), so
// this reimplements the same screen with MapLibre GL JS: GPS-centred start,
// tap-to-drop manhole/handhole pins with a condition sheet, walk-to-record
// routes, and markers/lines for what's already captured. Metro picks this
// file automatically for web builds; the native MapScreen.tsx is untouched.
//
// Bottom chrome (segmented Manhole/Handhole toggle + full-width Record
// Route button) follows the Claude Design redesign ("Field Survey App
// Redesign.dc.html", screen 3) — a white bottom panel rather than floating
// FABs for these two controls; zoom/recenter/layers stay as a FAB stack
// top-right, which that screen doesn't show but doesn't contradict either.
// Marker shapes (square = manhole, triangle = handhole) follow the explicit
// "clear distinction between them" instruction instead of the mockup's own
// circle/square convention — see pinStatus.ts.
import { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, Image, TextInput, ScrollView, Animated, Easing } from 'react-native';
import {
  Map as MaplibreMap, Marker, GeolocateControl,
  type MapMouseEvent, type StyleSpecification, type GeoJSONSource,
} from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { getFix, watchRoute, Fix } from '../gps';
import { notify } from '../notify';
import { confirmAction } from '../confirm';
import {
  enqueue, saveAsset, saveRoute, newId, listAssets, listRoutes, kvGet,
  deleteAsset, deleteOutbox, updateAssetPosition, updateOutboxPayload,
} from '../db';
import { authed } from '../auth';
import { COLOR, SPACE, RADIUS, ELEVATION, STATUS, MIN_TOUCH, FONT } from '../theme';
import { SecondaryFab } from '../components/Fab';
import { pinStatus, pinShape, type PinStatusName } from '../pinStatus';

type Mode = 'none' | 'manhole' | 'handhole' | 'record';
type LL = { lat: number; lon: number };

function haversine(a: number[], b: number[]): number {
  const R = 6371000, toR = Math.PI / 180;
  const dLat = (b[1] - a[1]) * toR, dLon = (b[0] - a[0]) * toR;
  const lat1 = a[1] * toR, lat2 = b[1] * toR;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
const lineLength = (pts: number[][]) =>
  pts.slice(1).reduce((s, p, i) => s + haversine(pts[i], p), 0);

// Central Abuja/FCT — every project sits somewhere in this district, so this
// is a reasonable last-resort centre if a project has no boundary yet AND
// the device has no GPS fix (e.g. reviewing from a desk with location
// permission denied). Not meant to be precise, just "in the right country".
const FCT_FALLBACK_CENTER: LL = { lat: 9.0765, lon: 7.3986 };

// Bounding-box centre of a GeoJSON Polygon/MultiPolygon — good enough for
// "where should the map open", doesn't need to be a true geometric centroid.
// Recurses through the nested coordinate arrays regardless of ring/hole depth.
function bboxCenter(geometry: { coordinates: any }): LL | null {
  let minLon = Infinity, minLat = Infinity, maxLon = -Infinity, maxLat = -Infinity;
  let found = false;
  (function walk(node: any) {
    if (Array.isArray(node) && typeof node[0] === 'number' && typeof node[1] === 'number') {
      const [lon, lat] = node;
      minLon = Math.min(minLon, lon); maxLon = Math.max(maxLon, lon);
      minLat = Math.min(minLat, lat); maxLat = Math.max(maxLat, lat);
      found = true;
      return;
    }
    if (Array.isArray(node)) node.forEach(walk);
  })(geometry?.coordinates);
  if (!found) return null;
  return { lat: (minLat + maxLat) / 2, lon: (minLon + maxLon) / 2 };
}

// Zero-config raster basemap (no API key). Switched from tile.openstreetmap.org
// to CARTO's tile CDN — confirmed live that OSM's raw tile server sends no
// Access-Control-Allow-Origin header, and MapLibre GL JS loads raster tiles
// via fetch() (not a plain <img> tag), so every tile request was being
// blocked by CORS in the browser console. CARTO's basemap CDN sends CORS
// headers and is free to use with attribution, which is included below per
// both CARTO's and OSM's usage policies.
// Satellite imagery uses Esri's World Imagery tile service — free, no API
// key required (same zero-config bar as the CARTO street basemap above),
// just attribution. Added as a second raster layer, hidden by default and
// toggled via the FAB stack, rather than swapping STYLE.sources wholesale —
// keeps both basemaps loaded so switching is instant with no re-fetch.
const STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png'],
      tileSize: 256,
      attribution: '© OpenStreetMap contributors © CARTO',
    },
    satellite: {
      type: 'raster',
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      tileSize: 256,
      // Esri's free World Imagery layer only guarantees high-res coverage
      // worldwide up to z17 — past that, areas without dedicated high-zoom
      // capture (much of the FCT outside central Abuja) return a tile with
      // "Map data not yet available at this zoom level" baked into the image
      // instead of a real photo. Capping maxzoom here makes MapLibre
      // overzoom (stretch) the last real z17 tile instead of fetching that
      // placeholder — a blurrier but genuine image rather than broken text.
      maxzoom: 17,
      attribution: 'Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    },
  },
  layers: [
    { id: 'osm', type: 'raster', source: 'osm' },
    { id: 'satellite', type: 'raster', source: 'satellite', layout: { visibility: 'none' } },
  ],
};

const emptyFC = (): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features: [] });

// A plain number for icon-size/circle-radius renders at a constant screen
// size regardless of zoom (the default "map pin" behaviour). Marker/pin
// shapes should instead scale with zoom — bigger when zoomed in close to
// judge exact placement, smaller when zoomed out so they don't clutter the
// view — so every marker size below is a zoom-interpolated expression
// rather than a bare number. The z18 stop is calibrated to the intended
// base size (the map's default zoom is 18); z14/z22 are half/double that.
function zoomSize(sizeAtZ18: number): any {
  return ['interpolate', ['linear'], ['zoom'], 14, sizeAtZ18 / 2, 18, sizeAtZ18, 22, sizeAtZ18 * 2];
}

// The map is full-bleed (position:absolute, inset:0) with no header to push
// floating controls below a phone's notch/status bar/PWA chrome, unlike
// every other screen (which has a real header View). Without this, the back
// button and FAB stack render at a flat 16px from the top — behind, or
// right up against, that system UI on real devices, which both looks wrong
// ("too high") and can make them untappable (taps in that strip get eaten
// by the OS/browser instead of reaching the page). env(safe-area-inset-top)
// requires viewport-fit=cover, already set by patch-pwa-html.js.
const SAFE_TOP = 'calc(env(safe-area-inset-top, 0px) + 16px)';

// Square (manhole) and triangle (handhole) marker icons are drawn on a
// canvas once per status colour and registered with MapLibre as images —
// cheaper than a second vector/SDF pipeline, and the palette is fixed (3
// statuses + 1 draft colour per shape), so precomputed static icons cover
// every case. Anything that isn't a manhole or handhole (joint_chamber,
// footway_box, other) falls back to a plain circle layer (no image needed).
function squareIconData(color: string, size = 22): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const r = 5, pad = 3, x = pad, y = pad, w = size - pad * 2, h = size - pad * 2;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#fff';
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

function triangleIconData(color: string, size = 24): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const pad = 3;
  ctx.beginPath();
  ctx.moveTo(size / 2, pad);
  ctx.lineTo(size - pad, size - pad);
  ctx.lineTo(pad, size - pad);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#fff';
  ctx.lineJoin = 'round';
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

// House icon (square body + triangular roof) for the NOC — the network
// reference layer's fixed physical facility, distinct from FAT/FDH's hollow
// rings so it reads as "the building", not another design point.
function houseIconData(color: string, size = 26): ImageData {
  const canvas = document.createElement('canvas');
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const pad = 3, roofY = pad, eaveY = size * 0.42, floorY = size - pad;
  const left = pad, right = size - pad, mid = size / 2;
  ctx.beginPath();
  ctx.moveTo(left, floorY);
  ctx.lineTo(left, eaveY);
  ctx.lineTo(mid, roofY);
  ctx.lineTo(right, eaveY);
  ctx.lineTo(right, floorY);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#fff';
  ctx.lineJoin = 'round';
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

// Injected once — the pulsing current-location marker (§10) needs a CSS
// keyframe that a StyleSheet.create() object can't express.
const PULSE_STYLE_ID = 'gp-pulse-marker-style';
function ensurePulseStyle() {
  if (document.getElementById(PULSE_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = PULSE_STYLE_ID;
  style.textContent = `
    .gp-pulse-marker { width: 16px; height: 16px; position: relative; }
    .gp-pulse-marker::before, .gp-pulse-marker::after {
      content: ''; position: absolute; inset: 0; border-radius: 9999px;
      background: ${COLOR.primary500};
    }
    .gp-pulse-marker::before {
      box-shadow: 0 0 0 2px #fff, 0 2px 6px rgba(13,27,75,0.35);
    }
    .gp-pulse-marker::after {
      inset: -14px;
      opacity: 0.3;
      animation: gp-pulse 1.8s ease-out infinite;
    }
    @keyframes gp-pulse {
      0% { transform: scale(0.6); opacity: 0.55; }
      100% { transform: scale(2.2); opacity: 0; }
    }
  `;
  document.head.appendChild(style);
}

// The draft (unsaved) pin is a real draggable DOM Marker rather than a
// style-layer feature, specifically so it can be dragged to fine-tune the
// exact spot — combined with the map's already-unrestricted zoom/pan, that's
// the "zoom in to confirm exact location" step before picking a condition
// and saving. Shapes are plain CSS (no canvas needed, unlike the saved-asset
// icons, since there's only ever one draft shape live at a time).
const DRAFT_MARKER_STYLE_ID = 'gp-draft-marker-style';
function ensureDraftMarkerStyle() {
  if (document.getElementById(DRAFT_MARKER_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = DRAFT_MARKER_STYLE_ID;
  style.textContent = `
    .gp-draft-square {
      width: 26px; height: 26px; border-radius: 6px;
      background: ${COLOR.accent500}; border: 2px solid #fff;
      box-shadow: 0 2px 6px rgba(13,27,75,0.4);
      cursor: grab;
    }
    .gp-draft-square:active { cursor: grabbing; }
    .gp-draft-triangle {
      width: 0; height: 0;
      border-left: 15px solid transparent;
      border-right: 15px solid transparent;
      border-bottom: 26px solid ${COLOR.accent500};
      filter: drop-shadow(0 2px 3px rgba(13,27,75,0.4));
      cursor: grab;
    }
    .gp-draft-triangle:active { cursor: grabbing; }
  `;
  document.head.appendChild(style);
}

export default function MapScreen({ onBack }: { onBack: () => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MaplibreMap | null>(null);
  const geolocateRef = useRef<GeolocateControl | null>(null);
  const locationMarkerRef = useRef<Marker | null>(null);
  const draftMarkerRef = useRef<Marker | null>(null);
  const [ready, setReady] = useState(false);
  // Map's initial centre — defaults to the current project's site, not the
  // surveyor's own position (see the init effect below). Independent of
  // userFix, which tracks the device's actual live GPS location.
  const [start, setStart] = useState<LL | null>(null);
  // Best-known live device location — feeds the "you are here" pulse marker
  // and the my-location FAB's recenter, but never the map's default view.
  const [userFix, setUserFix] = useState<LL | null>(null);
  const [mode, setMode] = useState<Mode>('none');
  const [pin, setPin] = useState<LL | null>(null);
  const [manholes, setManholes] = useState<any[]>([]);
  const [buildingPhotos, setBuildingPhotos] = useState<any[]>([]);
  const [routes, setRoutes] = useState<any[]>([]);
  const [recording, setRecording] = useState(false);
  const [recPts, setRecPts] = useState<number[][]>([]);   // [lon,lat]
  const [busy, setBusy] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [showNetwork, setShowNetwork] = useState(false);
  const [showSatellite, setShowSatellite] = useState(false);
  const [showBuildings, setShowBuildings] = useState(false);
  const [networkLoaded, setNetworkLoaded] = useState(false);
  const [networkFeatureCount, setNetworkFeatureCount] = useState(0);
  const [buildingsLoaded, setBuildingsLoaded] = useState(false);
  const [pendingCondition, setPendingCondition] = useState<string | null>(null);
  const [inspect, setInspect] = useState<{
    clientId: string; label: string; status: PinStatusName; condition?: string;
    synced: boolean; lat: number; lon: number;
  } | null>(null);
  // Tapped FAT/FDH/NOC from the read-only network reference layer — separate
  // from `inspect` (surveyor-captured manholes/handholes) since these carry
  // design-time properties (utilisation, capacity, ...) rather than
  // survey/condition state, and there's nothing to move or delete here.
  const [netInspect, setNetInspect] = useState<{
    kind: 'fat' | 'fdh' | 'noc'; lat: number; lon: number; props: Record<string, any>;
  } | null>(null);
  // Tapped building-photo house icon — view-only (no move/delete for this
  // capture type yet). serverId is null until the capture has synced, in
  // which case there's no photo to fetch remotely yet either.
  const [photoInspect, setPhotoInspect] = useState<{
    serverId: string | null; synced: boolean; lat: number; lon: number;
    loading: boolean; url: string | null; error: string | null;
  } | null>(null);
  // Set while an *existing* manhole/handhole is being repositioned (as
  // opposed to a brand-new one being created) — reuses the same draft-marker
  // + pin-sheet machinery as create, just routes Save to saveReposition()
  // instead of savePin() and skips the condition picker.
  const [editing, setEditing] = useState<{ clientId: string; synced: boolean } | null>(null);

  // Tapped building footprint on the map (see the 'buildings' source/layer
  // below) — a surveyor-facing edit form for the same PATCH BuildingScreen's
  // GPS-list flow already sends, plus "doesn't exist" (excludes it). Kept
  // separate from `inspect` since buildings are pre-existing office-imported
  // records being field-updated, not a surveyor-created point asset.
  const [buildingEdit, setBuildingEdit] = useState<{
    id: string; code: string | null; buildingType: string; address: string;
    units: string; drop: 'aerial' | 'underground' | ''; notes: string;
    lat: number; lon: number;
  } | null>(null);
  const [savingBuilding, setSavingBuilding] = useState(false);
  // Measured height of the white bottom panel (segmented pill + record
  // button) — the attribution strip is pinned just above it rather than
  // literally 8px from the screen edge, which the opaque panel would hide.
  const [panelHeight, setPanelHeight] = useState(160);
  // Pulses the record button's orange dot while recording — the button
  // itself stays navy throughout (Vol.4.1 §10 / doc §3: orange is reserved
  // for the record indicator and attention pins, never a full navy->orange
  // button swap).
  const recordPulse = useRef(new Animated.Value(1)).current;

  // A fresh tap (new pin) or leaving placement mode always starts the
  // condition choice over — otherwise a leftover selection from a previous
  // drop could get saved against a pin the surveyor never actually reviewed.
  useEffect(() => { setPendingCondition(null); }, [pin]);
  const stopRef = useRef<null | (() => void)>(null);
  const modeRef = useRef<Mode>('none');
  useEffect(() => { modeRef.current = mode; }, [mode]);

  useEffect(() => {
    if (!recording) { recordPulse.setValue(1); return; }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(recordPulse, { toValue: 0.25, duration: 700, easing: Easing.ease, useNativeDriver: true }),
        Animated.timing(recordPulse, { toValue: 1, duration: 700, easing: Easing.ease, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [recording]);

  async function reload() {
    const all = await listAssets();
    setManholes(all.filter((a) => a.kind === 'manhole'));
    setBuildingPhotos(all.filter((a) => a.kind === 'building_photo'));
    setRoutes(await listRoutes());
  }

  // Initial map centre + data load (once). Prefers the project's own
  // boundary over the surveyor's device position — a GPS-centred map was
  // opening on wherever the surveyor physically was (including reviewing
  // remotely from a different city/country entirely), not the district
  // actually being surveyed.
  useEffect(() => {
    ensurePulseStyle();
    ensureDraftMarkerStyle();
    (async () => {
      const pid = await kvGet('projectId');
      setProjectId(pid);

      // Best-effort live fix, independent of the map's default centre —
      // only feeds the pulse marker + my-location FAB fallback.
      getFix().then((f) => setUserFix({ lat: f.lat, lon: f.lon })).catch(() => {});

      let center: LL | null = null;
      if (pid) {
        try {
          const res = await authed(`/api/v1/projects/${pid}/boundary`);
          if (res.ok) center = bboxCenter((await res.json()).geometry);
        } catch { /* offline — fall through to GPS/default below */ }
      }
      if (!center) {
        // No project boundary yet (or offline) — fall back to the device's
        // own position, then a fixed Abuja/FCT point as a last resort.
        try { const f = await getFix(); center = { lat: f.lat, lon: f.lon }; }
        catch { center = FCT_FALLBACK_CENTER; }
      }
      setStart(center);

      await reload();
    })();
    return () => { stopRef.current?.(); };
  }, []);

  // Fetch the photo behind a tapped building-photo icon — lazily, only once
  // a marker is actually tapped (not preloaded for every capture). Reuses
  // the same generic media endpoint the sync engine uploads through and the
  // desktop app already reads from.
  useEffect(() => {
    if (!photoInspect || !photoInspect.serverId || !photoInspect.loading) return;
    const serverId = photoInspect.serverId;
    (async () => {
      try {
        const res = await authed(
          `/api/v1/projects/${projectId}/mobile/media?entity_type=building_photo&entity_id=${serverId}`);
        if (!res.ok) throw new Error('Could not load photo.');
        const body = await res.json();
        const url = body.media?.[0]?.view_url ?? null;
        setPhotoInspect((cur) => (cur && cur.serverId === serverId)
          ? { ...cur, loading: false, url, error: url ? null : 'No photo found.' } : cur);
      } catch (e: any) {
        setPhotoInspect((cur) => (cur && cur.serverId === serverId)
          ? { ...cur, loading: false, error: String(e?.message ?? e) } : cur);
      }
    })();
  }, [photoInspect, projectId]);

  // Network design reference layer (FAT/FDH + NOC) — fetched once per
  // project, lazily, and kept hidden until the surveyor asks for it via the
  // layers FAB. FAT/FDH silently stay empty if the project has no committed
  // design run yet (zones.geojson returns an empty FeatureCollection in that
  // case); the NOC is a fixed facility so it comes from its own dedicated
  // endpoint (the same one the desktop app uses — routing/noc.geojson) and
  // is always present regardless of design state. Both stay empty if we're
  // offline — this is context, not something field capture depends on.
  useEffect(() => {
    if (!ready || !projectId || networkLoaded) return;
    (async () => {
      try {
        const [zonesRes, nocRes] = await Promise.all([
          authed(`/api/v1/projects/${projectId}/design/zones.geojson`),
          authed(`/api/v1/projects/${projectId}/routing/noc.geojson`),
        ]);
        const zonesFeatures = zonesRes.ok ? (await zonesRes.json()).features ?? [] : [];
        const nocFeatures = nocRes.ok ? (await nocRes.json()).features ?? [] : [];
        const fc = { type: 'FeatureCollection', features: [...zonesFeatures, ...nocFeatures] };
        const src = mapRef.current?.getSource('network') as GeoJSONSource | undefined;
        src?.setData(fc as any);
        setNetworkFeatureCount(
          zonesFeatures.filter((f: any) => f.properties?.kind === 'fat' || f.properties?.kind === 'fdh').length);
        setNetworkLoaded(true);
      } catch { /* no connection — leave the layer empty, toggle stays usable */ }
    })();
  }, [ready, projectId, networkLoaded]);

  // Building footprints — the same polygons the office map shows, fetched
  // read-only (no Permission.BUILDING_EDIT required, just project
  // membership — see features.py's buildings_geojson) so a surveyor can tap
  // one directly instead of hunting a GPS-proximity list. Hidden by default,
  // like the network layer, and loaded once per project.
  useEffect(() => {
    if (!ready || !projectId || buildingsLoaded) return;
    (async () => {
      try {
        const res = await authed(`/api/v1/projects/${projectId}/buildings.geojson`);
        const fc = res.ok ? await res.json() : { type: 'FeatureCollection', features: [] };
        const src = mapRef.current?.getSource('buildings') as GeoJSONSource | undefined;
        src?.setData(fc as any);
        setBuildingsLoaded(true);
      } catch { /* no connection — leave the layer empty, toggle stays usable */ }
    })();
  }, [ready, projectId, buildingsLoaded]);

  // Create the map once we have a starting position.
  useEffect(() => {
    if (!start || !containerRef.current || mapRef.current) return;
    const map = new MaplibreMap({
      container: containerRef.current,
      style: STYLE,
      center: [start.lon, start.lat],
      zoom: 18,
      attributionControl: false,
    });

    // GeolocateControl is kept (for permission + tracking + its 'geolocate'
    // event) but visually replaced by our own themed pulsing marker + FABs
    // — the built-in control button and blue dot are hidden via CSS below.
    const geolocate = new GeolocateControl({
      positionOptions: { enableHighAccuracy: true }, trackUserLocation: true,
    });
    map.addControl(geolocate, 'top-right');
    geolocateRef.current = geolocate;

    map.on('load', () => {
      const topRight = containerRef.current?.querySelector('.maplibregl-ctrl-top-right') as HTMLElement | null;
      if (topRight) topRight.style.display = 'none';

      // The "you are here" pulse marker is created lazily by the userFix
      // effect below, once we actually know the device's position — not
      // here, since the map may be centred on the project site instead.

      map.addSource('manholes', { type: 'geojson', data: emptyFC() });
      // Circle layer: fallback for any type that isn't manhole/handhole
      // (joint_chamber, footway_box, other) — not reachable from this map's
      // two-mode UI today, kept for forward-compat with other capture paths.
      map.addLayer({
        id: 'manholes-circle', type: 'circle', source: 'manholes',
        filter: ['==', ['get', 'shape'], 'circle'],
        paint: {
          'circle-radius': zoomSize(16),
          'circle-color': ['match', ['get', 'status'],
            'synced', STATUS.synced, 'flagged', STATUS.flagged, STATUS.pending],
          'circle-stroke-width': 2, 'circle-stroke-color': '#fff',
        },
      });
      // Square (image) layer: manholes.
      (['synced', 'pending', 'flagged'] as PinStatusName[]).forEach((st) => {
        if (!map.hasImage(`sq-${st}`)) map.addImage(`sq-${st}`, squareIconData(STATUS[st]), { pixelRatio: 2 });
        if (!map.hasImage(`tri-${st}`)) map.addImage(`tri-${st}`, triangleIconData(STATUS[st]), { pixelRatio: 2 });
      });
      map.addLayer({
        id: 'manholes-square', type: 'symbol', source: 'manholes',
        filter: ['==', ['get', 'shape'], 'square'],
        layout: {
          'icon-image': ['concat', 'sq-', ['get', 'status']],
          'icon-size': zoomSize(2), 'icon-allow-overlap': true,
        },
      });
      // Triangle (image) layer: handholes.
      map.addLayer({
        id: 'manholes-triangle', type: 'symbol', source: 'manholes',
        filter: ['==', ['get', 'shape'], 'triangle'],
        layout: {
          'icon-image': ['concat', 'tri-', ['get', 'status']],
          'icon-size': zoomSize(2), 'icon-allow-overlap': true,
        },
      });

      // Quick building-photo captures — house icons (STATUS palette, like
      // manholes: grey while pending, teal once synced) so they read as
      // "another captured asset", distinct from the NOC's navy house below.
      (['synced', 'pending'] as const).forEach((st) => {
        if (!map.hasImage(`house-${st}`)) map.addImage(`house-${st}`, houseIconData(STATUS[st]), { pixelRatio: 2 });
      });
      map.addSource('building_photos', { type: 'geojson', data: emptyFC() });
      map.addLayer({
        id: 'building-photos', type: 'symbol', source: 'building_photos',
        layout: {
          'icon-image': ['concat', 'house-', ['case', ['get', 'synced'], 'synced', 'pending']],
          'icon-size': zoomSize(2), 'icon-allow-overlap': true,
        },
      });

      map.addSource('routes', { type: 'geojson', data: emptyFC() });
      map.addLayer({
        id: 'routes', type: 'line', source: 'routes',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        paint: { 'line-width': 4, 'line-color': COLOR.primary500 },
      });
      // The pending/unsaved drop pin is a draggable DOM Marker, not a style
      // layer — see the draftMarkerRef effect below and ensureDraftMarkerStyle.
      map.addSource('recording', { type: 'geojson', data: emptyFC() });
      map.addLayer({
        id: 'recording', type: 'line', source: 'recording',
        layout: { 'line-cap': 'round', 'line-join': 'round' },
        // Dashed while still being recorded — solid once saved (routes layer above).
        paint: { 'line-width': 3, 'line-color': COLOR.primary500, 'line-dasharray': [2, 2] },
      });

      // Network design reference layer (FAT/FDH) — hollow rings, deliberately
      // NOT using the teal/grey/orange status palette (that's reserved for
      // surveyor-captured asset state, §10) so this reads as planning/
      // reference data, not something to be "fixed" or synced. Hidden by
      // default; toggled via the layers FAB.
      map.addSource('network', { type: 'geojson', data: emptyFC() });
      map.addLayer({
        id: 'network-fat', type: 'circle', source: 'network',
        filter: ['==', ['get', 'kind'], 'fat'],
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': 6, 'circle-color': '#fff',
          'circle-stroke-width': 2, 'circle-stroke-color': COLOR.primary500,
        },
      });
      map.addLayer({
        id: 'network-fdh', type: 'circle', source: 'network',
        filter: ['==', ['get', 'kind'], 'fdh'],
        layout: { visibility: 'none' },
        paint: {
          'circle-radius': 10, 'circle-color': '#fff',
          'circle-stroke-width': 3, 'circle-stroke-color': COLOR.primary900,
        },
      });
      map.addLayer({
        id: 'network-fdh-label', type: 'symbol', source: 'network',
        filter: ['==', ['get', 'kind'], 'fdh'],
        layout: {
          visibility: 'none',
          'text-field': ['get', 'code'], 'text-size': 11,
          'text-offset': [0, 1.4], 'text-anchor': 'top',
        },
        paint: { 'text-color': COLOR.primary900, 'text-halo-color': '#fff', 'text-halo-width': 1.5 },
      });
      // NOC — the network's fixed physical facility, drawn as a house icon
      // so it reads as "the building" rather than another design point.
      if (!map.hasImage('house-noc')) {
        map.addImage('house-noc', houseIconData(COLOR.primary900), { pixelRatio: 2 });
      }
      map.addLayer({
        id: 'network-noc', type: 'symbol', source: 'network',
        filter: ['==', ['get', 'kind'], 'noc'],
        layout: {
          visibility: 'none', 'icon-image': 'house-noc',
          'icon-size': zoomSize(1.4), 'icon-allow-overlap': true,
        },
      });

      // Building footprints — tap-to-select for field updates (terrace/unit
      // count, "doesn't exist") instead of only the GPS-proximity list.
      // Hidden by default, toggled via the layers FAB, same as network above.
      map.addSource('buildings', { type: 'geojson', data: emptyFC() });
      map.addLayer({
        id: 'buildings-fill', type: 'fill', source: 'buildings',
        layout: { visibility: 'none' },
        paint: { 'fill-color': COLOR.primary500, 'fill-opacity': 0.15 },
      });
      map.addLayer({
        id: 'buildings-line', type: 'line', source: 'buildings',
        layout: { visibility: 'none' },
        paint: { 'line-color': COLOR.primary900, 'line-width': 1.25 },
      });

      setReady(true);
    });

    map.on('click', (e: MapMouseEvent) => {
      if (modeRef.current === 'manhole' || modeRef.current === 'handhole') {
        setPin({ lat: e.lngLat.lat, lon: e.lngLat.lng });
      }
    });

    // Tap an already-captured manhole/handhole to see what's already there
    // — only while not actively placing a new one, so placement taps always
    // win over inspecting whatever happens to be underneath the tap.
    const inspectHandler = (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
      if (modeRef.current !== 'none') return;
      const f = e.features?.[0];
      if (!f || f.geometry.type !== 'Point') return;
      const [lon, lat] = f.geometry.coordinates as [number, number];
      const p = f.properties ?? {};
      setInspect({
        clientId: p.client_id, label: p.label, status: p.status, condition: p.condition,
        synced: !!p.synced, lat, lon,
      });
    };
    map.on('click', 'manholes-circle', inspectHandler);
    map.on('click', 'manholes-square', inspectHandler);
    map.on('click', 'manholes-triangle', inspectHandler);
    (['manholes-circle', 'manholes-square', 'manholes-triangle'] as const).forEach((id) => {
      map.on('mouseenter', id, () => { if (modeRef.current === 'none') map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
    });

    // Tap a FAT, FDH, or the NOC on the network reference layer to see its
    // design-time details — read-only, so no move/delete, just a details
    // card. Same "not mid-placement" guard as the manhole inspect handler.
    const netInspectHandler = (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
      if (modeRef.current !== 'none') return;
      const f = e.features?.[0];
      if (!f || f.geometry.type !== 'Point') return;
      const [lon, lat] = f.geometry.coordinates as [number, number];
      const props = f.properties ?? {};
      setNetInspect({ kind: props.kind, lat, lon, props });
    };
    (['network-fat', 'network-fdh', 'network-fdh-label', 'network-noc'] as const).forEach((id) => {
      map.on('click', id, netInspectHandler);
      map.on('mouseenter', id, () => { if (modeRef.current === 'none') map.getCanvas().style.cursor = 'pointer'; });
      map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; });
    });

    // Tap a building-photo house icon to view it — view-only, no move/delete.
    map.on('click', 'building-photos', (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
      if (modeRef.current !== 'none') return;
      const f = e.features?.[0];
      if (!f || f.geometry.type !== 'Point') return;
      const [lon, lat] = f.geometry.coordinates as [number, number];
      const p = f.properties ?? {};
      setPhotoInspect({
        serverId: p.id ?? null, synced: !!p.synced, lat, lon,
        loading: !!p.id, url: null, error: null,
      });
    });
    map.on('mouseenter', 'building-photos', () => { if (modeRef.current === 'none') map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'building-photos', () => { map.getCanvas().style.cursor = ''; });

    // Tap a building footprint to edit its surveyed attributes (or flag it
    // as not existing) directly, rather than only via the GPS-proximity
    // list in the separate Building capture form.
    map.on('click', 'buildings-fill', (e: MapMouseEvent & { features?: GeoJSON.Feature[] }) => {
      if (modeRef.current !== 'none') return;
      const f = e.features?.[0];
      if (!f) return;
      const p = f.properties ?? {};
      if (!p.building_id) return;
      setBuildingEdit({
        id: p.building_id, code: p.code ?? null,
        buildingType: p.building_type || 'residential',
        address: p.address || '',
        units: p.units_surveyed ? String(p.units_surveyed) : '',
        drop: (p.drop_deployment as any) || '',
        notes: p.notes || '',
        lat: e.lngLat.lat, lon: e.lngLat.lng,
      });
    });
    map.on('mouseenter', 'buildings-fill', () => { if (modeRef.current === 'none') map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'buildings-fill', () => { map.getCanvas().style.cursor = ''; });

    geolocate.on('geolocate', (e: any) => {
      if (e?.coords) setUserFix({ lat: e.coords.latitude, lon: e.coords.longitude });
    });

    mapRef.current = map;
    return () => { map.remove(); mapRef.current = null; locationMarkerRef.current = null; draftMarkerRef.current = null; };
  }, [start]);

  // "You are here" pulse marker — created once we actually know the
  // device's position (from the background GPS fix or a 'geolocate' event),
  // and kept in sync as fresher fixes come in. Deliberately not tied to the
  // map's default centre (`start`), which may be the project site instead.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !userFix) return;
    if (locationMarkerRef.current) {
      locationMarkerRef.current.setLngLat([userFix.lon, userFix.lat]);
      return;
    }
    const el = document.createElement('div');
    el.className = 'gp-pulse-marker';
    locationMarkerRef.current = new Marker({ element: el })
      .setLngLat([userFix.lon, userFix.lat]).addTo(map);
  }, [ready, userFix]);

  // Keep the manhole/route layers in sync with captured data. The asset
  // currently being repositioned (if any) is left out here — it's shown
  // instead as the draggable draft marker below, so there's exactly one
  // marker on screen for it rather than two overlapping.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource('manholes') as GeoJSONSource | undefined;
    src?.setData({
      type: 'FeatureCollection',
      features: manholes
        .filter((m) => m.client_id !== editing?.clientId)
        .map((m) => ({
          type: 'Feature', geometry: { type: 'Point', coordinates: [m.lon, m.lat] },
          properties: {
            label: m.label, status: pinStatus(m), shape: pinShape(m),
            condition: m.sub, synced: !!m.synced, client_id: m.client_id,
          },
        })),
    });
  }, [manholes, ready, editing]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource('routes') as GeoJSONSource | undefined;
    src?.setData({
      type: 'FeatureCollection',
      features: routes.map((r) => ({
        type: 'Feature', geometry: { type: 'LineString', coordinates: JSON.parse(r.points) },
        properties: { synced: !!r.synced },
      })),
    });
  }, [routes, ready]);

  // Quick building-photo captures — house icons, view-only (see photoInspect
  // below). Separate source/layer from the manholes one above since these
  // carry no condition/shape classification, just a location + a photo.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource('building_photos') as GeoJSONSource | undefined;
    src?.setData({
      type: 'FeatureCollection',
      features: buildingPhotos.map((bp) => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: [bp.lon, bp.lat] },
        properties: { id: bp.server_id ?? null, client_id: bp.client_id, synced: !!bp.synced },
      })),
    });
  }, [buildingPhotos, ready]);

  // Draggable draft marker — lets the surveyor zoom in and nudge the exact
  // spot before picking a condition and saving, rather than only being able
  // to re-tap elsewhere. Reuses the same Marker instance across re-tap
  // repositions within one placement session (just moves it) and only
  // creates/destroys it when a placement session actually starts/ends.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    if (!pin || (mode !== 'manhole' && mode !== 'handhole')) {
      draftMarkerRef.current?.remove();
      draftMarkerRef.current = null;
      return;
    }

    if (draftMarkerRef.current) {
      draftMarkerRef.current.setLngLat([pin.lon, pin.lat]);
      return;
    }

    const el = document.createElement('div');
    el.className = mode === 'handhole' ? 'gp-draft-triangle' : 'gp-draft-square';
    const marker = new Marker({ element: el, draggable: true, anchor: 'center' })
      .setLngLat([pin.lon, pin.lat])
      .addTo(map);
    marker.on('dragend', () => {
      const ll = marker.getLngLat();
      setPin({ lat: ll.lat, lon: ll.lng });
    });
    draftMarkerRef.current = marker;
  }, [pin, mode, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const src = map.getSource('recording') as GeoJSONSource | undefined;
    src?.setData(recPts.length > 1
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: recPts }, properties: {} }] }
      : emptyFC());
  }, [recPts, ready]);

  async function savePin() {
    if (!pin || !pendingCondition) return;
    setBusy(true);
    try {
      const clientId = newId('mh');
      await saveAsset({ clientId, kind: 'manhole', lat: pin.lat, lon: pin.lon,
        accuracy: 0, label: mode, sub: pendingCondition });
      await enqueue({ clientId, kind: 'manhole', payload: {
        lon: pin.lon, lat: pin.lat, manhole_type: mode, condition: pendingCondition } });
      setPin(null); setMode('none'); await reload();
    } finally { setBusy(false); }
  }

  // Enters "move" for the asset currently shown in the inspect card — reuses
  // the pin/draft-marker/sheet machinery from create, distinguished by
  // `editing` being set. Falls back to 'manhole' shape for the handful of
  // types (joint_chamber, footway_box, other) this screen's two-mode UI
  // can't create but could theoretically inspect.
  function beginMove() {
    if (!inspect) return;
    setEditing({ clientId: inspect.clientId, synced: inspect.synced });
    setMode(inspect.label === 'handhole' ? 'handhole' : 'manhole');
    setPin({ lat: inspect.lat, lon: inspect.lon });
    setInspect(null);
  }

  async function saveReposition() {
    if (!pin || !editing) return;
    setBusy(true);
    try {
      await updateAssetPosition(editing.clientId, pin.lat, pin.lon);
      if (editing.synced) {
        // Already on the server — queue a PATCH for next sync rather than
        // touching the create payload (there isn't one any more).
        await enqueue({ clientId: newId('mhmv'), kind: 'manhole_reposition',
          payload: { manholeClientId: editing.clientId, lon: pin.lon, lat: pin.lat } });
      } else {
        // Never left the device yet — rewrite the still-queued create
        // payload in place so it's created at the right spot the first time,
        // instead of queuing a separate reposition for something that
        // hasn't been created server-side to reposition.
        await updateOutboxPayload(editing.clientId, (p) => ({ ...p, lon: pin.lon, lat: pin.lat }));
      }
      setPin(null); setMode('none'); setEditing(null);
      await reload();
      notify('Location updated', editing.synced
        ? "Saved on this device — will sync the new position next time you're online."
        : 'Saved locally.');
    } finally { setBusy(false); }
  }

  async function deleteExisting() {
    if (!inspect) return;
    const target = inspect;
    const ok = await confirmAction(`Delete this ${target.label || 'capture'}?`, target.synced
      ? "This removes it from your device now, and from the server next time you're online."
      : 'This removes it from your device — it never reached the server.');
    if (!ok) return;
    setBusy(true);
    try {
      await deleteAsset(target.clientId);
      if (target.synced) {
        await enqueue({ clientId: newId('mhdel'), kind: 'manhole_delete',
          payload: { manholeClientId: target.clientId } });
      } else {
        await deleteOutbox(target.clientId);
      }
      setInspect(null);
      await reload();
    } finally { setBusy(false); }
  }

  async function startRecord() {
    setRecPts([]); setRecording(true); setMode('record'); setPin(null); setEditing(null);
    try {
      stopRef.current = await watchRoute(8, (f: Fix) =>
        setRecPts((p) => [...p, [f.lon, f.lat]]));
    } catch (e: any) { notify('GPS', String(e?.message ?? e)); setRecording(false); }
  }

  async function stopRecord() {
    stopRef.current?.(); stopRef.current = null; setRecording(false);
    const pts = recPts;
    if (pts.length < 2) { notify('Route', 'Walk a bit further — need at least two points.'); setMode('none'); return; }
    setBusy(true);
    try {
      const clientId = newId('rt');
      const len = lineLength(pts);
      await saveRoute({ clientId, routeType: 'cable_route', points: pts, lengthM: len });
      await enqueue({ clientId, kind: 'route', payload: { points: pts, route_type: 'cable_route' } });
      setRecPts([]); setMode('none'); await reload();
      notify('Route saved', `${Math.round(len)} m over ${pts.length} points (offline).`);
    } finally { setBusy(false); }
  }

  function recenter() {
    if (geolocateRef.current) { geolocateRef.current.trigger(); return; }
    const map = mapRef.current;
    if (map && userFix) map.easeTo({ center: [userFix.lon, userFix.lat], zoom: 18 });
  }

  function toggleNetwork() {
    const map = mapRef.current;
    if (!map) return;
    const next = !showNetwork;
    if (next && !projectId) {
      notify('Network layer', 'Select a project first.');
    } else if (next && networkLoaded && networkFeatureCount === 0) {
      // The layer is toggling on correctly, but there's nothing to draw —
      // this project has no committed FAT/FDH design plotted yet. Without
      // this, the toggle looks broken (nothing visibly changes on the map).
      notify('Network layer', 'No FAT/FDH network design has been plotted for this project yet.');
    } else if (next && !networkLoaded) {
      notify('Network layer', "Still loading — try again in a moment, or check you're online.");
    }
    setShowNetwork(next);
    (['network-fat', 'network-fdh', 'network-fdh-label', 'network-noc'] as const).forEach((id) =>
      map.setLayoutProperty(id, 'visibility', next ? 'visible' : 'none'));
  }

  function toggleSatellite() {
    const map = mapRef.current;
    if (!map) return;
    const next = !showSatellite;
    setShowSatellite(next);
    map.setLayoutProperty('satellite', 'visibility', next ? 'visible' : 'none');
  }

  function toggleBuildings() {
    const map = mapRef.current;
    if (!map) return;
    const next = !showBuildings;
    if (next && !projectId) {
      notify('Buildings layer', 'Select a project first.');
    } else if (next && !buildingsLoaded) {
      notify('Buildings layer', "Still loading — try again in a moment, or check you're online.");
    }
    setShowBuildings(next);
    (['buildings-fill', 'buildings-line'] as const).forEach((id) =>
      map.setLayoutProperty(id, 'visibility', next ? 'visible' : 'none'));
  }

  async function saveBuildingEdit() {
    if (!buildingEdit) return;
    setSavingBuilding(true);
    try {
      const attrs: any = { building_type: buildingEdit.buildingType };
      if (buildingEdit.address) attrs.address = buildingEdit.address;
      if (buildingEdit.units) attrs.units_surveyed = parseInt(buildingEdit.units, 10);
      if (buildingEdit.drop) attrs.drop_deployment = buildingEdit.drop;
      if (buildingEdit.notes) attrs.notes = buildingEdit.notes;
      const clientId = newId('bld');
      await saveAsset({
        clientId, kind: 'building', lat: buildingEdit.lat, lon: buildingEdit.lon,
        accuracy: 0, label: buildingEdit.code || 'Unnumbered', sub: buildingEdit.buildingType,
      });
      await enqueue({ clientId, kind: 'building', payload: { buildingId: buildingEdit.id, attrs } });
      setBuildingEdit(null);
      notify('Building updated', "Saved on this device — will sync next time you're online.");
    } finally { setSavingBuilding(false); }
  }

  async function flagBuildingNotExisting() {
    if (!buildingEdit) return;
    const ok = await confirmAction(
      `Flag "${buildingEdit.code || 'this building'}" as not existing?`,
      "This removes it from the map and any network design — a manager can restore it from the office app if it's a mistake.");
    if (!ok) return;
    setSavingBuilding(true);
    try {
      const clientId = newId('bld');
      await saveAsset({
        clientId, kind: 'building', lat: buildingEdit.lat, lon: buildingEdit.lon,
        accuracy: 0, label: buildingEdit.code || 'Unnumbered', sub: 'flagged: does not exist',
      });
      await enqueue({
        clientId, kind: 'building_exclude',
        payload: { buildingId: buildingEdit.id,
                  reason: 'Surveyor: footprint does not exist on the ground.' },
      });
      setBuildingEdit(null);
      notify('Flagged', "Marked as not existing — will sync next time you're online.");
    } finally { setSavingBuilding(false); }
  }

  // Tapping the already-active mode again turns placement back off — the
  // redesign's 2-way pill (Drop Manhole | Drop Handhole) has no separate
  // "Off" segment, so toggle-off-on-repeat-tap is how you back out of it.
  function setAssetMode(next: 'manhole' | 'handhole') {
    setMode((m) => (m === next ? 'none' : next));
    setPin(null); setInspect(null); setEditing(null);
  }

  if (!start) return <View style={s.center}><ActivityIndicator color={COLOR.primary900} /></View>;

  return (
    <View style={{ flex: 1 }}>
      {/* @ts-ignore — a plain DOM div is the correct host for MapLibre on web */}
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />

      <TouchableOpacity style={s.backBtn} onPress={onBack}>
        <Text style={s.backIcon}>←</Text>
      </TouchableOpacity>

      {/* Pin-drop confirm sheet — the map's quick tap-to-drop flow stays a
          lightweight floating card (not the full BottomSheet form used for
          Manhole/Building capture), since it's a faster, separate interaction. */}
      {pin && (mode === 'manhole' || mode === 'handhole') && (
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>{editing ? `Move ${mode} to here?` : `Place ${mode} here?`}</Text>
          <Text style={s.sheetCoord}>{pin.lat.toFixed(6)}, {pin.lon.toFixed(6)}</Text>
          <Text style={s.sheetHint}>
            {editing
              ? 'Zoom in or drag the pin to fine-tune the new spot, then confirm below.'
              : 'Zoom in or drag the pin to fine-tune the spot, then confirm below.'}
          </Text>
          {!editing && (
            <View style={s.condRow}>
              {['good', 'fair', 'poor', 'damaged', 'unknown'].map((c) => (
                <TouchableOpacity key={c} disabled={busy} onPress={() => setPendingCondition(c)}
                  style={[s.cond, pendingCondition === c && s.condSelected]}>
                  <Text style={[s.condText, pendingCondition === c && s.condTextSelected]}>{c}</Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
          <TouchableOpacity style={[s.save, ((editing ? false : !pendingCondition) || busy) && { opacity: 0.5 }]}
            disabled={(editing ? false : !pendingCondition) || busy}
            onPress={editing ? saveReposition : savePin}>
            {busy
              ? <ActivityIndicator color="#fff" />
              : <Text style={s.saveText}>{editing ? 'Save new location' : `Save ${mode}`}</Text>}
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setPin(null); setEditing(null); }}>
            <Text style={s.cancel}>Cancel</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Existing-pin inspect card — shown when tapping an already-captured
          manhole/handhole outside placement mode; Move promotes it to the
          draggable draft flow above, Delete soft-deletes it (server-side
          for synced captures, local-only for ones that never synced). */}
      {inspect && (
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>{inspect.label || 'Manhole'}</Text>
          <Text style={s.sheetCoord}>{inspect.lat.toFixed(6)}, {inspect.lon.toFixed(6)}</Text>
          <View style={s.condRow}>
            {inspect.condition && (
              <View style={s.badgeChip}><Text style={s.badgeChipText}>{inspect.condition}</Text></View>
            )}
            <View style={[s.badgeChip, {
              backgroundColor: inspect.status === 'flagged' ? COLOR.accent500
                : inspect.status === 'synced' ? COLOR.success500 : COLOR.text500,
            }]}>
              <Text style={[s.badgeChipText, { color: '#fff' }]}>
                {inspect.status === 'flagged' ? 'flagged' : inspect.synced ? 'synced' : 'pending'}
              </Text>
            </View>
          </View>
          <View style={s.inspectActions}>
            <TouchableOpacity style={[s.inspectBtn, { backgroundColor: COLOR.surface100 }]}
              disabled={busy} onPress={beginMove}>
              <Text style={[s.inspectBtnText, { color: COLOR.text900 }]}>Move</Text>
            </TouchableOpacity>
            <TouchableOpacity style={[s.inspectBtn, { backgroundColor: COLOR.error }]}
              disabled={busy} onPress={deleteExisting}>
              {busy
                ? <ActivityIndicator color="#fff" />
                : <Text style={[s.inspectBtnText, { color: '#fff' }]}>Delete</Text>}
            </TouchableOpacity>
          </View>
          <TouchableOpacity onPress={() => setInspect(null)}><Text style={s.cancel}>Close</Text></TouchableOpacity>
        </View>
      )}

      {/* Network reference layer details — tapped FAT/FDH/NOC. Read-only
          design-time data (not survey state), so just a details card. */}
      {netInspect && (
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>
            {netInspect.kind === 'noc' ? (netInspect.props.name || 'NOC')
              : netInspect.kind === 'fdh' ? `FDH ${netInspect.props.code ?? ''}`
              : `FAT ${netInspect.props.zone_code ?? ''}`}
          </Text>
          <Text style={s.sheetCoord}>{netInspect.lat.toFixed(6)}, {netInspect.lon.toFixed(6)}</Text>
          {netInspect.kind === 'noc' && !!netInspect.props.address && (
            <Text style={s.sheetHint}>{netInspect.props.address}</Text>
          )}
          {netInspect.kind === 'fdh' && (
            <View style={s.netDetails}>
              <View style={s.netRow}><Text style={s.netLabel}>Premises</Text><Text style={s.netValue}>{netInspect.props.premises}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>FATs</Text><Text style={s.netValue}>{netInspect.props.fats}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Splitters</Text><Text style={s.netValue}>{netInspect.props.splitters}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Capacity</Text><Text style={s.netValue}>{netInspect.props.capacity}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Utilisation</Text><Text style={s.netValue}>{Number(netInspect.props.utilisation ?? 0).toFixed(0)}%</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Max reach</Text><Text style={s.netValue}>{Math.round(netInspect.props.reach_m ?? 0)} m</Text></View>
            </View>
          )}
          {netInspect.kind === 'fat' && (
            <View style={s.netDetails}>
              <View style={s.netRow}><Text style={s.netLabel}>Zone</Text><Text style={s.netValue}>{netInspect.props.zone_code}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Premises</Text><Text style={s.netValue}>{netInspect.props.premises}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Buildings</Text><Text style={s.netValue}>{netInspect.props.buildings}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Spare ports</Text><Text style={s.netValue}>{netInspect.props.spare_ports}</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Utilisation</Text><Text style={s.netValue}>{Number(netInspect.props.utilisation ?? 0).toFixed(0)}%</Text></View>
              <View style={s.netRow}><Text style={s.netLabel}>Max drop</Text><Text style={s.netValue}>{Math.round(netInspect.props.max_drop_m ?? 0)} m</Text></View>
              {!!netInspect.props.has_warning && (
                <View style={[s.badgeChip, { backgroundColor: COLOR.accent500, alignSelf: 'flex-start', marginTop: SPACE.sm }]}>
                  <Text style={[s.badgeChipText, { color: '#fff' }]}>has warnings</Text>
                </View>
              )}
            </View>
          )}
          <TouchableOpacity onPress={() => setNetInspect(null)}><Text style={s.cancel}>Close</Text></TouchableOpacity>
        </View>
      )}

      {/* Building photo — view-only, no move/delete for this capture type. */}
      {photoInspect && (
        <View style={s.sheet}>
          <Text style={s.sheetTitle}>Building photo</Text>
          <Text style={s.sheetCoord}>{photoInspect.lat.toFixed(6)}, {photoInspect.lon.toFixed(6)}</Text>
          {!photoInspect.synced ? (
            <Text style={s.sheetHint}>Saved on this device — the photo will be viewable here once it syncs.</Text>
          ) : photoInspect.loading ? (
            <ActivityIndicator color={COLOR.primary900} style={{ marginTop: SPACE.md }} />
          ) : photoInspect.url ? (
            <Image source={{ uri: photoInspect.url }} style={s.photoPreview} resizeMode="cover" />
          ) : (
            <Text style={s.sheetHint}>{photoInspect.error || 'No photo found.'}</Text>
          )}
          <TouchableOpacity onPress={() => setPhotoInspect(null)}><Text style={s.cancel}>Close</Text></TouchableOpacity>
        </View>
      )}

      {/* Tapped building footprint — field-update the surveyed attributes the
          office app's building_edit_service already accepts (type, unit
          count, address, drop deployment), or flag the footprint as not
          existing. Taller than the other sheets, so it scrolls internally
          rather than running off the top of a small screen. */}
      {buildingEdit && (
        <View style={[s.sheet, s.sheetTall]}>
          <ScrollView keyboardShouldPersistTaps="handled">
            <Text style={s.sheetTitle}>{buildingEdit.code || 'Building'}</Text>
            <Text style={s.sheetCoord}>{buildingEdit.lat.toFixed(6)}, {buildingEdit.lon.toFixed(6)}</Text>

            <Text style={s.beLabel}>Type</Text>
            <View style={s.condRow}>
              {['residential', 'terrace', 'commercial', 'mixed_use', 'institutional', 'religious', 'other'].map((t) => (
                <TouchableOpacity key={t} disabled={savingBuilding}
                  onPress={() => setBuildingEdit((b) => b && { ...b, buildingType: t })}
                  style={[s.cond, buildingEdit.buildingType === t && s.condSelected]}>
                  <Text style={[s.condText, buildingEdit.buildingType === t && s.condTextSelected]}>
                    {t.replace('_', ' ')}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
            {buildingEdit.buildingType === 'terrace' && (
              <Text style={s.beHint}>
                Row of terraces — set the number of units below so the auto drop
                deployment plans one drop per unit, not one for the whole row.
              </Text>
            )}

            <Text style={s.beLabel}>Number of units</Text>
            <TextInput style={s.beInput} keyboardType="number-pad" placeholder="e.g. 6"
              placeholderTextColor={COLOR.text500} value={buildingEdit.units}
              onChangeText={(v) => setBuildingEdit((b) => b && { ...b, units: v })} />

            <Text style={s.beLabel}>Address</Text>
            <TextInput style={s.beInput} placeholder="Street address" placeholderTextColor={COLOR.text500}
              value={buildingEdit.address} onChangeText={(v) => setBuildingEdit((b) => b && { ...b, address: v })} />

            <Text style={s.beLabel}>Drop deployment</Text>
            <View style={s.condRow}>
              {(['aerial', 'underground'] as const).map((d) => (
                <TouchableOpacity key={d} disabled={savingBuilding}
                  onPress={() => setBuildingEdit((b) => b && { ...b, drop: b.drop === d ? '' : d })}
                  style={[s.cond, buildingEdit.drop === d && s.condSelected]}>
                  <Text style={[s.condText, buildingEdit.drop === d && s.condTextSelected]}>{d}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={[s.save, savingBuilding && { opacity: 0.6 }]}
              disabled={savingBuilding} onPress={saveBuildingEdit}>
              {savingBuilding ? <ActivityIndicator color="#fff" /> : <Text style={s.saveText}>Save changes</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={[s.inspectBtn, { backgroundColor: COLOR.error, marginTop: SPACE.sm }]}
              disabled={savingBuilding} onPress={flagBuildingNotExisting}>
              <Text style={[s.inspectBtnText, { color: '#fff' }]}>This building doesn't exist</Text>
            </TouchableOpacity>
            <TouchableOpacity onPress={() => setBuildingEdit(null)} disabled={savingBuilding}>
              <Text style={s.cancel}>Close</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      )}

      {/* Recording banner */}
      {recording && (
        <View style={s.recBanner}>
          <View style={s.recDot} />
          <Text style={s.recText}>Recording route · {recPts.length} pts · {Math.round(lineLength(recPts))} m</Text>
        </View>
      )}

      {!recording && (mode === 'manhole' || mode === 'handhole') && !pin && (
        <View style={s.hint}><Text style={s.hintText}>Tap the map to drop the {mode} pin</Text></View>
      )}

      {/* Top-right FAB stack — zoom/recenter/layers (not shown in the
          redesign comp, additive and non-conflicting with it). */}
      <View style={s.fabStack}>
        <SecondaryFab icon="▧" active={showBuildings} onPress={toggleBuildings} />
        <SecondaryFab icon="▦" active={showNetwork} onPress={toggleNetwork} />
        <SecondaryFab icon="◐" active={showSatellite} onPress={toggleSatellite} />
        <SecondaryFab icon="+" onPress={() => mapRef.current?.zoomIn()} />
        <SecondaryFab icon="−" onPress={() => mapRef.current?.zoomOut()} />
        <SecondaryFab icon="◎" onPress={recenter} />
      </View>

      {/* Bottom panel — 2-way segmented Manhole/Handhole toggle + full-width
          Record Route button, per the redesign's screen 3. */}
      <View style={s.bottomPanel} onLayout={(e) => setPanelHeight(e.nativeEvent.layout.height)}>
        <View style={s.assetPillRow}>
          <TouchableOpacity style={[s.assetPill, mode === 'manhole' && s.assetPillActive]}
            onPress={() => setAssetMode('manhole')}>
            <Text style={[s.assetPillText, mode === 'manhole' && s.assetPillTextActive]}>Drop Manhole</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[s.assetPill, mode === 'handhole' && s.assetPillActive]}
            onPress={() => setAssetMode('handhole')}>
            <Text style={[s.assetPillText, mode === 'handhole' && s.assetPillTextActive]}>Drop Handhole</Text>
          </TouchableOpacity>
        </View>
        {!recording ? (
          <TouchableOpacity style={s.recordBtn} onPress={startRecord}>
            <View style={s.recordDot} />
            <Text style={s.recordText}>Start Recording Route</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={s.recordBtn} onPress={stopRecord} disabled={busy}>
            {busy
              ? <ActivityIndicator color="#fff" />
              : <Animated.View style={[s.recordDot, { opacity: recordPulse }]} />}
            <Text style={s.recordText}>{busy ? 'Saving…' : 'Stop Recording'}</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Attribution strip — a licence requirement for the OSM/CARTO tiles
          (and Esri's when satellite is toggled on), so it's real provider
          text rather than the doc's placeholder string, styled per §3:
          centred, Space Mono, muted. Pinned just above the bottom panel
          (measured via onLayout above) since that opaque panel would
          otherwise cover a literal "8px from the screen bottom" position. */}
      <View style={[s.attribution, { bottom: panelHeight + 8 }]} pointerEvents="none">
        <Text style={s.attributionText} numberOfLines={1}>
          {showSatellite
            ? 'MAP DATA © ESRI, MAXAR, EARTHSTAR GEOGRAPHICS'
            : 'MAP DATA © OPENSTREETMAP CONTRIBUTORS © CARTO'}
        </Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  backBtn: {
    position: 'absolute', top: SAFE_TOP as any, left: 16, width: 44, height: 44, borderRadius: RADIUS.full,
    backgroundColor: COLOR.surface0, alignItems: 'center', justifyContent: 'center', ...ELEVATION[2],
  },
  backIcon: { fontSize: 20, color: COLOR.primary900, fontWeight: '700' },
  fabStack: { position: 'absolute', top: SAFE_TOP as any, right: SPACE.md, alignItems: 'flex-end', gap: SPACE.sm + 2 },
  bottomPanel: { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: COLOR.surface0, borderTopWidth: 1, borderTopColor: COLOR.borderDefault, padding: SPACE.md - 2, paddingBottom: SPACE.lg - 2 },
  assetPillRow: { flexDirection: 'row', gap: 6, backgroundColor: COLOR.surface100, borderRadius: RADIUS.full, padding: 6, marginBottom: SPACE.sm + 4 },
  assetPill: { flex: 1, minHeight: MIN_TOUCH, borderRadius: RADIUS.full, alignItems: 'center', justifyContent: 'center' },
  assetPillActive: { backgroundColor: COLOR.surface0, ...ELEVATION[1] },
  assetPillText: { fontSize: 13, fontWeight: '700', color: COLOR.text500 },
  assetPillTextActive: { color: COLOR.text900 },
  recordBtn: { height: 52, borderRadius: RADIUS.sm, backgroundColor: COLOR.primary900, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACE.sm },
  recordDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLOR.accent500 },
  recordText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  hint: { position: 'absolute', top: SAFE_TOP as any, alignSelf: 'center', backgroundColor: COLOR.primary900, borderRadius: RADIUS.full, paddingHorizontal: SPACE.md - 2, paddingVertical: SPACE.sm - 1 },
  hintText: { color: '#fff', fontSize: 13 },
  recBanner: { position: 'absolute', top: SAFE_TOP as any, alignSelf: 'center', backgroundColor: COLOR.surface0, borderRadius: RADIUS.full, paddingHorizontal: SPACE.md - 2, paddingVertical: SPACE.sm, flexDirection: 'row', alignItems: 'center', ...ELEVATION[2] },
  recDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLOR.error, marginRight: SPACE.sm },
  recText: { color: COLOR.text900, fontWeight: '600' },
  sheet: { position: 'absolute', bottom: 150, left: SPACE.md, right: SPACE.md, backgroundColor: COLOR.surface0, borderRadius: RADIUS.lg, padding: SPACE.md, ...ELEVATION[4] },
  sheetTall: { maxHeight: '65vh' as any, overflow: 'hidden' as any },
  beLabel: { fontSize: 13, color: COLOR.text500, marginBottom: 6, marginTop: SPACE.sm + 2 },
  beInput: { backgroundColor: COLOR.surface100, borderRadius: RADIUS.sm, padding: 10, borderWidth: 1, borderColor: COLOR.borderDefault, color: COLOR.text900, minHeight: MIN_TOUCH - 4 },
  beHint: { color: COLOR.text500, fontSize: 12, marginTop: 6 },
  sheetTitle: { fontWeight: '700', color: COLOR.text900, fontSize: 15 },
  sheetCoord: { color: COLOR.text500, marginTop: 2 },
  sheetHint: { color: COLOR.text500, fontSize: 12, marginTop: 4, marginBottom: SPACE.sm + 2 },
  condRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  cond: { backgroundColor: COLOR.surface100, borderRadius: RADIUS.full, paddingHorizontal: SPACE.sm + 4, paddingVertical: SPACE.sm - 1, minHeight: MIN_TOUCH - 8 },
  condSelected: { backgroundColor: COLOR.primary900 },
  condText: { color: COLOR.text900, fontWeight: '600', fontSize: 13 },
  condTextSelected: { color: '#fff' },
  save: { backgroundColor: COLOR.primary900, borderRadius: RADIUS.md, paddingVertical: SPACE.sm + 4, alignItems: 'center', marginTop: SPACE.md - 4, minHeight: MIN_TOUCH },
  saveText: { color: '#fff', fontWeight: '700', fontSize: 15 },
  badgeChip: { backgroundColor: COLOR.surface100, borderRadius: RADIUS.full, paddingHorizontal: SPACE.sm + 4, paddingVertical: SPACE.sm - 1 },
  badgeChipText: { color: COLOR.text900, fontWeight: '600', fontSize: 13 },
  inspectActions: { flexDirection: 'row', gap: SPACE.sm, marginTop: SPACE.md - 4 },
  inspectBtn: { flex: 1, borderRadius: RADIUS.md, paddingVertical: SPACE.sm + 4, alignItems: 'center', minHeight: MIN_TOUCH },
  inspectBtnText: { fontWeight: '700', fontSize: 15 },
  photoPreview: { width: '100%', height: 200, borderRadius: RADIUS.md, marginTop: SPACE.sm, backgroundColor: COLOR.surface100 },
  netDetails: { marginTop: SPACE.sm },
  netRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 3 },
  netLabel: { color: COLOR.text500, fontSize: 13 },
  netValue: { color: COLOR.text900, fontWeight: '600', fontSize: 13 },
  cancel: { color: COLOR.primary700, textAlign: 'center', marginTop: SPACE.sm + 4 },
  attribution: { position: 'absolute', left: 0, right: 0, alignItems: 'center', paddingHorizontal: SPACE.md },
  attributionText: { fontFamily: FONT.mono, fontSize: 10, lineHeight: 12, color: COLOR.text500 },
});
