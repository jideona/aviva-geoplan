const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, message: string,
              public kind: 'user' | 'admin' = 'user',
              public remedy?: string) {
    super(message)
  }
}

// Anything can subscribe to API failures — the toast surface does.
type ErrListener = (e: ApiError) => void
const errListeners = new Set<ErrListener>()
export function onApiError(fn: ErrListener): () => void {
  errListeners.add(fn)
  return () => { errListeners.delete(fn) }
}

let accessToken: string | null = sessionStorage.getItem('geoplan.access')
let refreshToken: string | null = sessionStorage.getItem('geoplan.refresh')

export function setTokens(access: string | null, refresh: string | null) {
  accessToken = access
  refreshToken = refresh
  if (access && refresh) {
    sessionStorage.setItem('geoplan.access', access)
    sessionStorage.setItem('geoplan.refresh', refresh)
  } else {
    sessionStorage.removeItem('geoplan.access')
    sessionStorage.removeItem('geoplan.refresh')
  }
}

export function hasSession() {
  return accessToken !== null
}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  if (init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  return fetch(`${BASE}${path}`, { ...init, headers })
}

async function refresh(): Promise<boolean> {
  if (!refreshToken) return false
  const res = await fetch(`${BASE}/api/v1/auth/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken }),
  })
  if (!res.ok) return false
  const data = await res.json()
  setTokens(data.access_token, data.refresh_token)
  return true
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res = await raw(path, init)
  if (res.status === 401 && refreshToken && !path.includes('/auth/')) {
    if (await refresh()) res = await raw(path, init)
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    let kind: 'user' | 'admin' = res.status >= 500 ? 'admin' : 'user'
    let remedy: string | undefined
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail)) {
        detail = body.detail.map((d: { msg: string }) => d.msg).join('; ')
      }
      if (body.kind) kind = body.kind
      if (body.remedy) remedy = body.remedy
    } catch { /* keep the generic message */ }
    if (res.status === 401) setTokens(null, null)
    const err = new ApiError(res.status, detail, kind, remedy)
    errListeners.forEach((fn) => fn(err))
    throw err
  }
  return res.status === 204 ? (undefined as T) : res.json()
}

export const api = {
  readiness: (id: string) =>
    request<Readiness>(`/api/v1/projects/${id}/readiness`),
  ready: () => request<{ status: string; schema_applied: string | null
                         schema_latest: string | null
                         pending_migrations: string[]
                         action: string | null }>('/api/v1/health/ready'),
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>('/api/v1/auth/login', {
      method: 'POST', body: JSON.stringify({ email, password }),
    }),
  me: () => request<User>('/api/v1/auth/me'),
  listProjects: () => request<Project[]>('/api/v1/projects'),
  getProject: (id: string) => request<Project>(`/api/v1/projects/${id}`),
  createProject: (payload: NewProject) =>
    request<Project>('/api/v1/projects', {
      method: 'POST', body: JSON.stringify(payload),
    }),
  getBoundary: (id: string) => request<Boundary>(`/api/v1/projects/${id}/boundary`),
  importOverture: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportSummary>(`/api/v1/projects/${id}/imports/overture-buildings`, {
      method: 'POST', body: form,
    })
  },
  importOsmRoads: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<ImportSummary>(`/api/v1/projects/${id}/imports/osm-roads`, {
      method: 'POST', body: form,
    })
  },
  runAssignment: (id: string, maxDistance: number) =>
    request<AssignmentResult>(`/api/v1/projects/${id}/street-assignment/run`, {
      method: 'POST',
      body: JSON.stringify({ max_distance_m: maxDistance, only_unassigned: false }),
    }),
  nameStreet: (id: string, streetId: string, body:
      { name: string; source: string; note?: string }) =>
    request<NamedStreet>(`/api/v1/projects/${id}/naming/streets/${streetId}`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  consolidateStreets: (id: string) =>
    request<{ streets_merged: number; segments_absorbed: number
              streets_remaining: number; named_streets: number; note: string }>(
      `/api/v1/projects/${id}/naming/consolidate`, { method: 'POST' }),
  deleteStreetsByCode: (id: string, codes: string[]) =>
    request<{ deleted: number; deleted_codes: string[]; not_found: string[] }>(
      `/api/v1/projects/${id}/streets/delete-by-code`, {
        method: 'POST', body: JSON.stringify({ codes }),
      }),
  deleteStreet: (id: string, streetId: string) =>
    request<{ deleted: number; code: string }>(
      `/api/v1/projects/${id}/streets/${streetId}`, { method: 'DELETE' }),
  nameSources: () =>
    request<{ sources: NameSourceOption[] }>('/api/v1/projects/x/naming/sources'),
  clearance: (id: string) =>
    request<Clearance>(`/api/v1/projects/${id}/naming/clearance`),
  importFieldData: (id: string, file: File, surveyDate?: string, surveyor?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (surveyDate) form.append('survey_date', surveyDate)
    if (surveyor) form.append('surveyor', surveyor)
    return request<FieldImportResult>(`/api/v1/projects/${id}/field-data/import`, {
      method: 'POST', body: form,
    })
  },
  matchingQueue: (id: string) =>
    request<MatchingQueue>(`/api/v1/projects/${id}/field-data/streets`),
  matchCandidates: (id: string, recordedId: string) =>
    request<Candidates>(`/api/v1/projects/${id}/field-data/streets/${recordedId}/candidates`),
  media: (id: string, entityType: string, entityId: string) =>
    request<{ media: MediaItem[] }>(
      `/api/v1/projects/${id}/mobile/media?entity_type=${entityType}&entity_id=${entityId}`),
  confirmMatch: (id: string, recordedId: string, streetId: string) =>
    request<{ street_code: string; name: string; length_delta_pct: number | null }>(
      `/api/v1/projects/${id}/field-data/streets/${recordedId}/match`,
      { method: 'POST', body: JSON.stringify({ street_id: streetId }) }),
  importPerimeters: (id: string, file: File) => {
    const form = new FormData(); form.append('file', file)
    return request<{ created: number; updated: number
                     outside_boundary: number; buildings_linked: number }>(
      `/api/v1/projects/${id}/parcels/perimeters`, { method: 'POST', body: form })
  },
  importMarkers: (id: string, file: File) => {
    const form = new FormData(); form.append('file', file)
    return request<{ markers: number; matched: number; orphaned: number
                     parcels_with_markers: number }>(
      `/api/v1/projects/${id}/parcels/markers`, { method: 'POST', body: form })
  },
  importNamePoints: (id: string, file: File) => {
    const form = new FormData(); form.append('file', file)
    return request<{ points: number; parcels_named: number
                     already_named: number; orphaned_points: number
                     conflict_count: number
                     conflicts: { parcel_code: string; existing: string
                                  point: string }[] }>(
      `/api/v1/projects/${id}/parcels/name-points`, { method: 'POST', body: form })
  },
  listParcels: (id: string) =>
    request<ParcelListing>(`/api/v1/projects/${id}/parcels`),
  renameParcel: (id: string, parcelId: string, name: string) =>
    request<{ parcel_code: string; name: string }>(
      `/api/v1/projects/${id}/parcels/${parcelId}/name`,
      { method: 'POST', body: JSON.stringify({ name }) }),
  attachUnits: (id: string) =>
    request<{ parcels: number; matched: number; disagreement_count: number
              disagreements: { parcel: string; workbook_estate: string
                               markers: number; workbook_buildings: number
                               footprints_inside: number }[]
              note: string }>(
      `/api/v1/projects/${id}/parcels/attach-units`, { method: 'POST' }),
  parcelSummary: (id: string) =>
    request<ParcelSummary>(`/api/v1/projects/${id}/parcels/summary`),
  parcelsGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/parcels.geojson`),
  estates: (id: string) =>
    request<EstateWorklist>(`/api/v1/projects/${id}/field-data/estates`),
  premisesModel: (id: string) =>
    request<PremisesModel>(`/api/v1/projects/${id}/field-data/premises-model`),
  designRules: () => request<DesignRuleInfo>('/api/v1/projects/x/design/rules'),
  currentDesign: (id: string) => request<Design>(`/api/v1/projects/${id}/design`),
  runDesign: (id: string, rules: DesignRuleInput) =>
    request<DesignRunResult>(`/api/v1/projects/${id}/design/run`, {
      method: 'POST', body: JSON.stringify(rules),
    }),
  createBuilding: (id: string, geometry: GeoJSON.Polygon, source: string) =>
    request<{ id: string; area_sqm: number; licence_class: string
              commercial_ready: boolean }>(
      `/api/v1/projects/${id}/buildings`,
      { method: 'POST', body: JSON.stringify({ geometry, source }) }),
  excludeBuilding: (id: string, buildingId: string, reason?: string) =>
    request<{ excluded: boolean }>(
      `/api/v1/projects/${id}/buildings/${buildingId}/exclude`,
      { method: 'PATCH', body: JSON.stringify({ excluded: true, reason }) }),
  deleteBuilding: (id: string, buildingId: string) =>
    request<{ deleted: string }>(`/api/v1/projects/${id}/buildings/${buildingId}`,
      { method: 'DELETE' }),
  moveFat: (id: string, zoneId: string, lon: number, lat: number) =>
    request<{ zone_code: string }>(
      `/api/v1/projects/${id}/design/fat/${zoneId}/position`,
      { method: 'PATCH', body: JSON.stringify({ lon, lat }) }),
  moveFdh: (id: string, fdhId: string, lon: number, lat: number) =>
    request<{ fdh_code: string }>(
      `/api/v1/projects/${id}/design/fdh/${fdhId}/position`,
      { method: 'PATCH', body: JSON.stringify({ lon, lat }) }),
  fatSchedule: (id: string) =>
    request<{ fats: { fat_code: string; premises: number
                      buildings: { code: string; area_sqm: number
                                   units: number | null; type: string
                                   verification: string }[] }[]
              count: number; note: string }>(
      `/api/v1/projects/${id}/fat-schedule`),
  routesGeoJSON: (id: string, phase: number) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/routing/phase/${phase}/geojson`),
  routesFullGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/routing/full/geojson`),
  designGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/design/zones.geojson`),
  designStaleness: (id: string) =>
    request<{ has_design: boolean; stale: boolean; buildings_changed: number;
              corridors_changed: number; ran_at: string | null;
              can_rerun: boolean }>(
      `/api/v1/projects/${id}/design/staleness`),
  rerunDesign: (id: string) =>
    request<{ design_run_id: string }>(
      `/api/v1/projects/${id}/design/rerun`, { method: 'POST' }),
  corridorsGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/corridors.geojson`),
  detectImport: (id: string, geojson: unknown, dryRun = false) =>
    request<{ candidates: number; imported: number; would_import: number;
              duplicates_skipped: number; merged_overlaps: number;
              outside_boundary: number; invalid: number; dry_run: boolean;
              commercial_ready: boolean; note: string;
              preview?: { type: string; features: GeoJSON.Feature[] } }>(
      `/api/v1/projects/${id}/buildings/detect-import`, {
        method: 'POST', body: JSON.stringify({ geojson, dry_run: dryRun }),
      }),
  clearDetected: (id: string) =>
    request<{ deleted: number }>(
      `/api/v1/projects/${id}/buildings/detected`, { method: 'DELETE' }),
  cleanupBuildings: (id: string, minAreaSqm: number, maxCircularity: number, dryRun: boolean) =>
    request<{ candidates: number; tiny: number; round: number; excluded: number;
              dry_run: boolean; note: string;
              preview?: { type: string; features: GeoJSON.Feature[] } }>(
      `/api/v1/projects/${id}/buildings/cleanup`, {
        method: 'POST',
        body: JSON.stringify({ min_area_sqm: minAreaSqm, max_circularity: maxCircularity, dry_run: dryRun }),
      }),
  createCorridor: (id: string, geometry: GeoJSON.Geometry,
                   corridorType: string, source: string) =>
    request<{ id: string; corridor_type: string; length_m: number;
              commercial_ready: boolean }>(
      `/api/v1/projects/${id}/corridors`, {
        method: 'POST',
        body: JSON.stringify({ geometry, corridor_type: corridorType, source }),
      }),
  dropsGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[];
              properties: { drop_limit_m: number | null; served: number;
                            unserved: number; over_limit: number;
                            routed: number; straight: number } }>(
      `/api/v1/projects/${id}/design/drops.geojson`),
  coverage: (id: string) =>
    request<SurveyCoverage>(`/api/v1/projects/${id}/walkthrough/coverage`),
  currency: (id: string) =>
    request<CurrencyReport>(`/api/v1/projects/${id}/walkthrough/currency`),
  walkthroughPack: (id: string) =>
    `${BASE}/api/v1/projects/${id}/walkthrough/pack.xlsx`,
  designPackUrl: (id: string) =>
    `${BASE}/api/v1/projects/${id}/design/pack.xlsx`,
  setZoneDropDeployment: (id: string, zoneCode: string,
                          deployment: 'aerial' | 'underground' | null) =>
    request<{ zone_code: string; deployment: string | null
              buildings_updated: number }>(
      `/api/v1/projects/${id}/design/zones/${encodeURIComponent(zoneCode)}/drop-deployment`, {
        method: 'POST', body: JSON.stringify({ deployment }),
      }),
  setAerialShare: (id: string, share: number) =>
    request<{ aerial_drop_share: number }>(
      `/api/v1/projects/${id}/design/aerial-share`, {
        method: 'PUT', body: JSON.stringify({ share }),
      }),
  designScenarios: (id: string, scenarios: object[]) =>
    request<{ scenarios: ScenarioResult[]; note: string }>(
      `/api/v1/projects/${id}/design/scenarios`, {
        method: 'POST', body: JSON.stringify({ scenarios }),
      }),
  designTopologyUrl: (id: string, fmt: 'svg' | 'png' | 'pdf' = 'svg') =>
    `${BASE}/api/v1/projects/${id}/design/topology.${fmt}`,
  designSchematicUrl: (id: string, fmt: 'svg' | 'png' | 'pdf' = 'svg') =>
    `${BASE}/api/v1/projects/${id}/design/schematic.${fmt}`,
  openInTab: async (url: string) => {
    const res = await fetch(url, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
    if (!res.ok) {
      let detail = `Failed (${res.status})`
      try { detail = (await res.json()).detail ?? detail } catch { /* keep */ }
      throw new ApiError(res.status, detail)
    }
    const blob = await res.blob()
    window.open(URL.createObjectURL(blob), '_blank')
  },
  namingQueue: (id: string) =>
    request<NamingQueue>(`/api/v1/projects/${id}/street-assignment/naming-queue`),
  importStreets: (id: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<ImportSummary>(`/api/v1/projects/${id}/imports/streets`, {
      method: 'POST', body: form,
    })
  },
  register: (id: string, params: URLSearchParams) =>
    request<RegisterPage>(`/api/v1/projects/${id}/register?${params}`),
  registerSummary: (id: string) =>
    request<RegisterSummary>(`/api/v1/projects/${id}/register/summary`),
  attribution: (id: string, purpose: string) =>
    request<Attribution>(`/api/v1/projects/${id}/register/attribution?purpose=${purpose}`),
  exportUrl: (id: string, fmt: 'csv' | 'xlsx' | 'geojson', params: URLSearchParams) =>
    `${BASE}/api/v1/projects/${id}/register/export.${fmt}?${params}`,
  download: async (url: string, filename: string) => {
    const res = await fetch(url, {
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    })
    if (!res.ok) {
      let detail = `Export failed (${res.status})`
      try { detail = (await res.json()).detail ?? detail } catch { /* keep */ }
      throw new ApiError(res.status, detail)
    }
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filename
    a.click()
    URL.revokeObjectURL(a.href)
  },
  areasGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/design/areas.geojson`),
  areaPackUrl: (id: string, quadrant: string) =>
    `${BASE}/api/v1/projects/${id}/design/area/${quadrant}/pack.xlsx`,
  ringGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[]
              properties?: { fdhs_on_ring: number; order: string[]
                             ring_trench_m: number; tree_feeder_m: number
                             incremental_trench_m: number; ring_cable_m: number
                             unreachable_fdhs: string[]; note: string } }>(
      `/api/v1/projects/${id}/routing/ring/geojson`),
  nocGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/routing/noc.geojson`),
  buildingsGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/buildings.geojson`),
  streetsGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/streets.geojson`),
  manholesGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/mobile/manholes.geojson`),
  buildingPhotosGeoJSON: (id: string) =>
    request<{ type: string; features: GeoJSON.Feature[] }>(
      `/api/v1/projects/${id}/mobile/building-photos.geojson`),
  listStreets: (id: string) => request<Street[]>(`/api/v1/projects/${id}/streets`),
  licenceSummary: (id: string) =>
    request<LicenceSummary>(`/api/v1/projects/${id}/licence-summary`),
  uploadBoundary: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Boundary>(`/api/v1/projects/${id}/boundary`, {
      method: 'POST', body: form,
    })
  },
  uploadStock: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<StockUploadResult>('/api/v1/inventory/upload', {
      method: 'POST', body: form,
    })
  },
  listStock: () => request<{ count: number; items: StockItem[] }>('/api/v1/inventory'),
  stockComparison: (id: string) =>
    request<StockComparisonResult>(`/api/v1/projects/${id}/design/stock-comparison`),
  // Full design pack as a single Word document. The aerial screenshot is
  // captured client-side from the live map canvas (see ProjectMap's
  // captureAerial) and posted alongside — the backend can't reconstruct a
  // faithful render of the interactive map headlessly, at whatever
  // zoom/layers the user had on screen.
  wordReport: async (id: string, aerialDataUrl: string | null, filenameHint: string) => {
    const form = new FormData()
    if (aerialDataUrl) {
      const blob = await (await fetch(aerialDataUrl)).blob()
      form.append('aerial', blob, 'aerial.png')
    }
    const res = await fetch(`${BASE}/api/v1/projects/${id}/design/pack.docx`, {
      method: 'POST',
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      body: form,
    })
    if (!res.ok) {
      let detail = `Export failed (${res.status})`
      try { detail = (await res.json()).detail ?? detail } catch { /* keep */ }
      throw new ApiError(res.status, detail)
    }
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = filenameHint
    a.click()
    URL.revokeObjectURL(a.href)
  },
  // Deployment task tracking — phase 1 of replacing the "Deployment plan"
  // monday.com board (see GeoPlan_Deployment_PM_Proposal.docx).
  deploymentTasks: (id: string, filters?: { area?: string; status?: string; assignee_id?: string }) => {
    const q = new URLSearchParams()
    if (filters?.area) q.set('area', filters.area)
    if (filters?.status) q.set('status', filters.status)
    if (filters?.assignee_id) q.set('assignee_id', filters.assignee_id)
    const qs = q.toString()
    return request<{ tasks: DeploymentTask[] }>(
      `/api/v1/projects/${id}/deployment/tasks${qs ? `?${qs}` : ''}`)
  },
  deploymentSummary: (id: string) =>
    request<DeploymentSummary>(`/api/v1/projects/${id}/deployment/tasks/summary`),
  deploymentAssignees: (id: string) =>
    request<{ users: DeploymentAssignee[] }>(`/api/v1/projects/${id}/deployment/assignees`),
  createDeploymentTask: (id: string, payload: DeploymentTaskInput) =>
    request<DeploymentTask>(`/api/v1/projects/${id}/deployment/tasks`, {
      method: 'POST', body: JSON.stringify(payload),
    }),
  updateDeploymentTask: (id: string, taskId: string, payload: Partial<DeploymentTaskInput>) =>
    request<DeploymentTask>(`/api/v1/projects/${id}/deployment/tasks/${taskId}`, {
      method: 'PATCH', body: JSON.stringify(payload),
    }),
  deleteDeploymentTask: (id: string, taskId: string) =>
    request<void>(`/api/v1/projects/${id}/deployment/tasks/${taskId}`, { method: 'DELETE' }),
}

export interface ScenarioResult {
  label: string
  error?: string
  rules: { fat_port_count: number; spare_port_ratio: number
           usable_ports: number; max_drop_length_m: number
           min_premises_per_fat: number; max_fdh_distribution_m: number
           noc_anchored: boolean }
  fats: number
  fdhs: number
  splitters: number
  served_buildings: number
  served_premises: number
  unassigned_buildings: number
  avg_fat_utilisation_pct: number
  trench_m: number
  feeder_cable_m: number
  distribution_cable_m: number
  drop_cable_m: number
  duct_sharing_saving_m: number
  chambers: { handholes: number; manholes_at_fdh: number
              manholes_on_runs: number }
  fats_unreachable: number
  warnings: number
}

export interface User {
  id: string; email: string; full_name: string
  organisation_id: string; roles: string[]; permissions: string[]
}

export const TASK_AREAS = ['ug_network', 'access', 'other'] as const
export const TASK_STATUSES = ['not_started', 'in_progress', 'blocked', 'done'] as const
export type TaskArea = typeof TASK_AREAS[number]
export type TaskStatus = typeof TASK_STATUSES[number]

export interface DeploymentTaskRef { id: string; full_name: string; email: string }

export interface DeploymentTask {
  id: string; project_id: string; title: string
  area: TaskArea; status: TaskStatus
  assignee: DeploymentTaskRef | null
  start_date: string | null; end_date: string | null; overdue: boolean
  updates: string | null; issues: string | null; has_issue: boolean
  entity_type: string | null; entity_id: string | null
  created_by: DeploymentTaskRef | null
  created_at: string; updated_at: string
}

export interface DeploymentTaskInput {
  title: string; area: TaskArea; status: TaskStatus
  assignee_id?: string | null
  start_date?: string | null; end_date?: string | null
  updates?: string | null; issues?: string | null
}

export interface DeploymentAssignee {
  id: string; full_name: string; email: string; roles: string[]
}

export interface DeploymentSummary {
  total: number
  by_area: Record<string, Record<string, number>>
  by_status: Record<string, number>
  overdue: number
  open_issues: number
  percent_done: number
}

export interface Project {
  id: string; name: string; client: string | null; country: string
  state: string | null; city: string | null; district: string
  code_prefix: string; metric_crs_epsg: number
  project_type: string; network_technology: string
  design_capacity: number | null; expected_takeup_rate: number | null
  design_horizon: string | null; status: string; notes: string | null
  created_at: string; updated_at: string
  has_boundary: boolean; boundary_area_sqkm: number | null
}

export interface NewProject {
  name: string; district: string; client?: string
  state?: string; city?: string; metric_crs_epsg?: number
  project_type?: string; network_technology?: string
}

export interface Boundary {
  id: string; project_id: string; area_sqkm: number
  source_filename: string; verification_state: string
  created_at: string; geometry: GeoJSON.Geometry
}

export interface ImportSummary {
  created: number; updated: number; unchanged: number
  skipped_outside_boundary: number; skipped_too_small: number
  skipped_protected: number; invalid_geometry: number
  licence_classes: Record<string, number>
  datasets: Record<string, number>
  share_alike_present: boolean
}

export interface Street {
  id: string; street_code: string; name: string | null
  name_state: 'confirmed' | 'identified' | 'unnamed'
  name_source: string | null; length_m: number
  road_class: string; licence_class: string; verification_state: string
  building_count: number
}

export interface LicenceSummary {
  total: number
  by_class: Record<string, number>
  share_alike_count: number
  share_alike_pct: number
  blocks_commercial_delivery: boolean
  note: string
}

export interface AssignmentResult {
  total: number; assigned: number; unassigned: number
  high_confidence: number; needs_review: number; low_confidence: number
  needs_field_name: number; skipped_protected?: number; max_distance_m?: number
}

export interface NamingQueue {
  unnamed_streets: number
  buildings_affected: number
  streets: { id: string; street_code: string; name: string | null
             name_source: string | null; road_class: string
             length_m: number; building_count: number }[]
}

export interface NamedStreet {
  id: string; street_code: string; name: string
  name_source: string; licence_class: string
  verification_state: string; needs_field_name: boolean
}

export interface NameSourceOption {
  value: string; licence_class: string; verification_state: string
  commercial_ready: boolean; note: string
}

export interface Clearance {
  clear_for_commercial_delivery: boolean
  note: string
  name_sources: Record<string, number>
  sources_requiring_re_sourcing: string[]
  streets_requiring_re_sourcing: number
  remedy: string
}

export interface RegisterRow {
  id: string; building_code: string | null
  street_code: string | null; street_name: string | null
  footprint_area_sqm: number; building_type: string; use_type: string
  floors_reported: number | null; units_surveyed: number | null
  premises_estimated: number | null
  assignment_confidence: number | null
  assignment_distance_m: number | null
  assignment_reason: string | null
  source_dataset: string | null; licence_class: string
  verification_state: string; survey_status: string
}

export interface RegisterPage {
  total: number; limit: number; offset: number
  filter_description: string; rows: RegisterRow[]
}

export interface RegisterSummary {
  buildings: number; assigned_to_street: number; unassigned: number
  assigned_pct: number; streets: number; streets_named: number
  streets_unnamed: number; total_footprint_sqm: number
  median_footprint_sqm: number | null; buildings_surveyed: number
  premises_estimated_total: number; premises_basis: string
  by_verification_state: Record<string, number>
  by_licence_class: Record<string, number>
}

export interface Attribution {
  project: string; generated: string; purpose: string
  blocked: boolean; reason: string | null
  attribution: string[]
  sources: { name: string; licence: string | null
             licence_class: string; feature_count: number }[]
}

export interface CurrencyReport {
  total: number
  by_currency: Record<string, number>
  median_age_years: number | null
  oldest_age_years: number | null
  requires_field_check: number
  requires_field_check_pct: number
  bands: Record<string, { label: string; survey_priority: number; note: string }>
  note: string
}

export interface FieldImportResult {
  recorded_streets_added: number; recorded_streets_skipped: number
  premises_observations: number; buildings_observed: number
  units_observed: number
}

export interface RecordedStreet {
  id: string; name: string; recorded_length_m: number | null
  match_status: string; matched_street_id: string | null
  length_delta_pct: number | null
}

export interface MatchingQueue {
  total: number; confirmed: number; unmatched: number
  streets: RecordedStreet[]
}

export interface MediaItem {
  id: string; entity_type: string; entity_id: string; kind: string
  object_key: string; content_type: string | null; caption: string | null
  uploaded: boolean; captured_at: string | null; view_url?: string | null
}

export interface Candidates {
  recorded: { id: string; name: string; recorded_length_m: number | null
              match_status: string }
  candidates: { street_id: string; street_code: string; road_class: string
                length_m: number; delta_pct: number | null
                existing_name: string | null
                name_similarity: number | null
                name_match: 'strong' | 'possible' | null
                crosses_boundary: boolean }[]
  candidates_within_tolerance: number
  strong_name_matches: number
  note: string
}

export interface PremisesModel {
  available: boolean
  reason?: string
  version?: string
  observations?: number
  buildings_covered?: number
  bands?: Record<string, {
    sample_size: number; buildings_covered: number
    replication: number; distinct_estates: number
    median: number; mean: number
    p25: number; p75: number; min: number; max: number
    well_evidenced: boolean }>
  sampling_bias?: { comparable: boolean; representative?: boolean
                    max_divergence_pp?: number; note: string }
  district_total?: { available: boolean; reason?: string
                     premises_estimate?: number; interval_low?: number
                     interval_high?: number; note?: string }
}

export interface DesignRuleInput {
  split_stage: string
  fdh_split_ratio: number
  fat_port_count: number
  spare_port_ratio: number
  max_drop_length_m: number
  min_premises_per_fat: number
  assumed_premises_per_building: number
  max_fat_road_offset_m: number
  noc_anchored?: boolean
  max_fdh_distribution_m?: number
}

export interface DesignRuleInfo {
  splitter_ratios: number[]
  defaults: DesignRuleInput
  engine_version: string
}

export interface DesignZone {
  id: string; zone_code: string
  building_count: number; premises_count: number
  splitter_ratio: number; usable_ports: number; spare_ports: number
  utilisation_pct: number; max_drop_m: number; avg_drop_m: number
  road_offset_m: number | null
  premises_assumed: boolean; warnings: string[]; locked: boolean
}

export interface FdhRow {
  code: string; premises: number; fats: number; splitters: number
  capacity: number; utilisation_pct: number; reach_m: number
}

export interface Design {
  design_run_id: string | null
  engine_version?: string; ran_at?: string; run_by?: string
  rules: Partial<DesignRuleInput>
  summary: Record<string, number | string | object>
  warnings: string[]
  zones: DesignZone[]
  fdhs?: FdhRow[]
}

export interface DesignRunResult {
  design_run_id: string
  zones: number; buildings_served: number; premises_served: number
  premises_total: number; unassigned_buildings: number
  max_drop_m: number; avg_zone_premises: number
  premises_assumed_count: number; engine_version: string
  warnings: string[]
}

export interface EstateEntry {
  estate: string; buildings: number; units: number
  street_hint: string | null
  street_id: string | null; street_name: string | null
  match_score: number
}

export interface EstateWorklist {
  available: boolean
  reason?: string
  estates_total?: number; located?: number; pending?: number
  units_located?: number; units_pending?: number
  buildings_located?: number; buildings_pending?: number
  worklist?: EstateEntry[]
  located_estates?: EstateEntry[]
  note?: string
}

export interface SurveyCoverage {
  available: boolean
  reason?: string
  cell_size_m?: number
  cells_total?: number; cells_with_coverage?: number
  cells_without_coverage?: number
  buildings_total?: number; buildings_in_surveyed_areas?: number
  coverage_pct?: number; units_located?: number
  spatially_representative?: boolean
  uncovered_cells?: { cell: string; centre_lat: number; centre_lon: number
                      buildings: number; coverage_pct: number }[]
  note?: string
}

export interface ParcelSummary {
  available: boolean
  reason?: string
  parcels?: number; total_area_sqm?: number
  buildings_inside_parcels?: number; buildings_total?: number
  coverage_pct?: number; parcels_with_units?: number
  units_total?: number; parcels_with_markers?: number
}

export interface ParcelRow {
  id: string; parcel_code: string; name: string
  raw_name: string | null; survey_code: string | null
  area_sqm: number; buildings: number; markers: number
  units: number | null; needs_name: boolean
  verification_state: string
}

export interface ParcelListing {
  total: number; needing_name: number; parcels: ParcelRow[]
}

export interface StockUploadResult {
  replaced: number; inserted: number
  categories: Record<string, number>
  unmatched_headers: string[]
  warnings: string[]
}

export interface StockItem {
  id: string; stock_code: string | null; category: string
  subcategory: string | null; manufacturer: string | null
  product_name: string; model: string | null
  quantity: number; uom: string; match_key: string | null
  unit_cost: number | null; condition: string | null
  warehouse: string | null; source_filename: string | null
  remarks: string | null
}

export interface StockComparisonLine {
  section: string; item: string; uom: string
  required: number; in_stock: number | null
  shortfall: number | null; surplus: number | null
  note?: string; matched_products?: string[]
}

export interface StockComparisonResult {
  stock_comparison: StockComparisonLine[]
  warnings: string[]
}

export interface ReadinessStep {
  key: string; label: string
  status: 'done' | 'pending' | 'blocked'
  detail: string; action: string | null; blocked_by: string | null
}
export interface Readiness {
  project: string; steps: ReadinessStep[]; complete: boolean
  next_step: ReadinessStep | null
  blocked_steps: ReadinessStep[]; summary: string
}
