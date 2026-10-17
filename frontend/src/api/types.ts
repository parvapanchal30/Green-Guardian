// Hand-written to mirror the backend schemas for now. To be replaced by types generated from
// /openapi.json (docs/FRONTEND_ARCHITECTURE.md) once the API surface grows.

export type WorkspaceMode = 'green_management' | 'agricultural_production'
export type Role = 'owner' | 'admin' | 'manager' | 'worker' | 'viewer'

export interface User {
  id: string
  email: string
  name: string
  phone: string | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface Workspace {
  id: string
  name: string
  mode: WorkspaceMode
  timezone: string
  settings: Record<string, unknown>
  created_at: string
  role: Role
}

export interface Member {
  user_id: string
  email: string
  name: string
  role: Role
}

export type Stage = 'mvp' | 'v2' | 'v3' | 'v4'

export interface Capability {
  key: string
  label: string
  technique: string
  stage: Stage
  available: boolean
  reason: string | null
}

export interface HourlyWeather {
  time: string
  precipitation_mm: number | null
  precipitation_probability_pct: number | null
  temperature_c: number | null
  et0_mm: number | null
  soil_moisture: Record<string, number>
}

export interface Forecast {
  latitude: number
  longitude: number
  timezone: string
  source: string
  attribution: string
  fetched_at: string
  hourly: HourlyWeather[]
}

export interface ProblemBody {
  code: string
  detail: string
  status: number
  errors?: { loc: string[]; msg: string; type: string }[]
}

// ---------------------------------------------------------------- vertical slice (assets -> observations -> issues -> tasks)

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type HealthBand = 'healthy' | 'at_risk' | 'critical'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type AssetKind = 'tree' | 'plant' | 'crop_batch' | 'shrub' | 'other'
export type LocationKind = 'site' | 'field' | 'zone' | 'plot'

export interface LocationItem {
  id: string
  name: string
  kind: LocationKind
  parent_id: string | null
  latitude: number | null
  longitude: number | null
  attributes: Record<string, unknown>
}

export interface SpeciesItem {
  id: string
  category: string
  common_name: string
  scientific_name: string | null
  is_global: boolean
}

export interface AssetState {
  health_score: number | null
  health_band: HealthBand | null
  health_observed_at: string | null
  last_observed_at: string | null
  open_issue_count: number
  open_task_count: number
  last_resolved_at: string | null
}

export interface Asset {
  id: string
  label: string
  kind: AssetKind
  tracking_mode: 'individual' | 'population'
  tag_code: string | null
  estimated_count: number | null
  current_stage: string
  species_id: string | null
  species_name: string | null
  location_id: string | null
  location_name: string | null
  latitude: number | null
  longitude: number | null
  planted_at: string | null
  attributes: Record<string, unknown>
  notes: string | null
  created_at: string
  archived_at: string | null
  state: AssetState
}

export interface Attachment {
  name: string
  content_type: string
  url?: string
  storage_key?: string
  caption?: string
}

export interface Observation {
  id: string
  asset_id: string | null
  observed_at: string
  observer_id: string | null
  kind: string
  source: string
  health_score: number | null
  symptoms: string[]
  notes: string | null
  data: Record<string, unknown>
  attachments: Attachment[]
  supersedes_id: string | null
  created_at: string
}

export type Method = 'rule' | 'statistical' | 'model' | 'llm'

export interface Recommendation {
  id: string
  rule_key: string
  method: Method
  asset_id: string
  title: string
  explanation: string
  evidence: Record<string, unknown>
  proposed_action: Record<string, unknown>
  severity: Severity
  status: 'open' | 'accepted' | 'dismissed' | 'expired'
  accepted_entity_type: string | null
  accepted_entity_id: string | null
  dismissed_reason: string | null
  created_at: string
  decided_at: string | null
}

export interface ObservationCreated {
  observation: Observation
  recommendations: Recommendation[]
}

export interface IssueHistory {
  from_state: string | null
  to_state: string
  actor_id: string | null
  note: string | null
  at: string
}

export interface Issue {
  id: string
  key: string
  title: string
  description: string | null
  category: string
  severity: Severity
  workflow_key: string
  state: string
  is_open: boolean
  asset_id: string | null
  asset_label: string | null
  location_id: string | null
  assignee_id: string | null
  reporter_id: string | null
  source: 'manual' | 'observation' | 'agent' | 'model'
  origin_observation_id: string | null
  recommendation_id: string | null
  opened_at: string
  updated_at: string
  resolved_at: string | null
  resolution_outcome: string | null
  resolution_notes: string | null
  resolved_by: string | null
  version: number
}

export interface IssueDetail extends Issue {
  history: IssueHistory[]
  evidence: Observation[]
  tasks: Task[]
  allowed_transitions: string[]
}

export interface Workflow {
  key: string
  label: string
  states: string[]
  initial: string
  terminal: string[]
  transitions: Record<string, string[]>
}

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'cancelled'

export interface Task {
  id: string
  key: string
  type: string
  title: string
  description: string | null
  issue_id: string | null
  issue_key: string | null
  asset_id: string | null
  asset_label: string | null
  location_id: string | null
  assignee_id: string | null
  priority: 'p1' | 'p2' | 'p3' | 'p4'
  status: TaskStatus
  source: string
  due_at: string | null
  started_at: string | null
  completed_at: string | null
  completion_notes: string | null
  overdue: boolean
  created_at: string
  updated_at: string
  version: number
}

export interface TaskDetail extends Task {
  history: { from_status: string | null; to_status: string; actor_id: string | null; note: string | null; at: string }[]
  allowed_transitions: string[]
}

export interface TimelineEvent {
  at: string
  type: 'observation' | 'issue' | 'task'
  ref_id: string
  key: string | null
  title: string
  detail: string | null
  actor_id: string | null
}

export interface RuleInfo {
  key: string
  method: string
  description: string
  parameters: Record<string, number>
}

export interface AgentRun {
  evaluated_assets: number
  created: Recommendation[]
  rules: RuleInfo[]
  note: string
}

// ------------------------------------------------------------------ dashboard read model
export interface DashboardKpi { key: string; label: string; available: boolean; value: number | null; unit: string | null; basis: string | null; reason: string | null }
export interface DashboardActivity { at: string; type: 'observation' | 'issue' | 'task'; ref_id: string; asset_id: string | null; key: string | null; title: string; detail: string | null }
export interface Dashboard {
  mode: string
  as_of: string
  filters: { location_id: string | null; kind: string | null }
  assets: { total: number; by_kind: Record<string, number>; health: { healthy: number; at_risk: number; critical: number; unknown: number } }
  work: {
    open_issues: number; open_issues_by_severity: Record<string, number>; open_tasks: number; overdue_tasks: number
    tasks_due_next_7_days: number; inspections_due: number; inspection_interval_days: number; open_recommendations: number
  }
  kpis: DashboardKpi[]
  recent_activity: DashboardActivity[]
}

// ------------------------------------------------------------------ map read model (GeoJSON, one layer registry)
export type MapFilter = 'all' | 'healthy' | 'at_risk' | 'critical' | 'open_issues' | 'tasks'
export interface MapLayerInfo { key: string; label: string; description: string; available: boolean; stage: string; geometry: 'point' | 'polygon' | 'raster'; requires: string | null }
export interface MapAssetProps {
  asset_id: string; label: string; kind: string; tracking_mode: string; estimated_count: number | null; species: string | null
  location_id: string | null; location_name: string | null; health_band: HealthBand | null; health_score: number | null
  open_issue_count: number; open_task_count: number; position_source: 'asset' | 'location'
}
export interface MapFeature { type: 'Feature'; id: string; geometry: { type: 'Point'; coordinates: [number, number] }; properties: MapAssetProps }
export interface MapCounts { all: number; healthy: number; at_risk: number; critical: number; open_issues: number; tasks: number; unlocated: number }
export interface MapFeatureCollection {
  type: 'FeatureCollection'; layer: string; filter: MapFilter; features: MapFeature[]; counts: MapCounts
  bbox: [number, number, number, number] | null; truncated: boolean
}

// ------------------------------------------------------------------ evidence (photos)
export interface Evidence {
  id: string; asset_id: string; observation_id: string | null; issue_id: string | null; uploaded_by: string
  original_filename: string | null; content_type: string; size_bytes: number; sha256: string; width: number; height: number
  caption: string | null; created_at: string; content_path: string
}
