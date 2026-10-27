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
  request_id?: string | null
  retry_after_s?: number
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
  assets: number // living assets placed here
  needs_attention: number // of those, at risk or critical
  schedules: number // active recurring inspections of the location
}

export interface SpeciesItem {
  id: string
  category: string
  common_name: string
  scientific_name: string | null
  is_global: boolean
  assets: number // live assets of this workspace that use it
  plants: number | null // estimated plants across its crop batches
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
  /** False once the asset left the lifecycle (dead, failed, removed, replaced). */
  is_active: boolean
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
  /** Traceability: the run that produced it (null when evaluated inline on an observation) and the rule's version. */
  agent_run_id: string | null
  rule_version: number | null
  /** Follow-up: what eventually happened to the work it led to. */
  outcome: 'task_completed' | 'task_cancelled' | 'issue_resolved' | 'issue_closed' | 'deferral_applied' | null
  outcome_at: string | null
  outcome_detail: string | null
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
  actions: ActionRecord[]
  verification: Verification
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
  type: 'observation' | 'issue' | 'task' | 'lifecycle' | 'harvest' | 'action'
  ref_id: string
  key: string | null
  title: string
  detail: string | null
  actor_id: string | null
}

export interface RuleInfo {
  key: string
  method: string
  version?: number
  description: string
  parameters: Record<string, number>
}

/** One entry of the agent's execution history (manual or scheduled). */
export interface AgentRunRecord {
  id: string
  trigger: 'manual' | 'scheduled'
  status: 'running' | 'succeeded' | 'failed'
  requested_by: string | null
  worker_id: string | null
  started_at: string
  finished_at: string | null
  duration_s: number | null
  evaluated_assets: number
  findings: number
  recommendations_created: number
  recommendations_expired: number
  rules: RuleInfo[]
  diagnostics: { weather?: { requested?: boolean; locations?: number; unavailable?: number; no_location?: number; source?: string | null }; skipped?: Record<string, number>; already_open?: number; dismissed_recently?: number }
  error: string | null
}

export interface AgentRun {
  run: AgentRunRecord | null
  evaluated_assets: number
  created: Recommendation[]
  expired: number
  rules: RuleInfo[]
  note: string
}

// ------------------------------------------------------------------ dashboard read model
export interface DashboardKpi { key: string; label: string; available: boolean; value: number | null; unit: string | null; basis: string | null; reason: string | null }
export interface DashboardActivity {
  at: string; type: 'observation' | 'issue' | 'task'; ref_id: string; asset_id: string | null; key: string | null; title: string; detail: string | null
  /** The parts of the line (ADR-081); absent from older servers. */
  subject?: string | null; from_state?: string | null; to_state?: string | null; note?: string | null; health_score?: number | null; symptoms?: string[]
}
export interface Dashboard {
  mode: string
  as_of: string
  filters: { location_id: string | null; kind: string | null }
  assets: { total: number; exited: number; by_kind: Record<string, number>; health: { healthy: number; at_risk: number; critical: number; unknown: number } }
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

// ------------------------------------------------------------------ audit trail (read-only)
export interface AuditEvent {
  id: string; occurred_at: string; actor_id: string | null; actor_name: string | null; action: string
  outcome: 'success' | 'failure' | 'denied'; target_type: string | null; target_id: string | null
  request_id: string | null; client_ip: string | null; details: Record<string, unknown>
}
export interface AuditMeta { actions: string[]; target_types: string[]; retention_days: number; min_retention_days: number }


// ------------------------------------------------------------------ datasets (Stage D)
export type DatasetStatus = 'proposed' | 'under_review' | 'approved' | 'rejected'
export type LabelStatus = 'unreviewed' | 'under_review' | 'accepted' | 'rejected' | 'corrected'
export type ImageOrigin = 'publisher_created' | 'third_party_licensed' | 'third_party_scraped' | 'unknown'
export type Tri = 'yes' | 'no' | 'unknown'

export interface DatasetEvidenceRecord {
  id: string
  url: string
  kind: string
  scope: 'images' | 'annotations' | 'both'
  licence_spdx: string
  excerpt: string
  official: boolean
  accessed_at: string
  recorded_by: string | null
  recorded_at: string
}

export interface DatasetHistoryEntry {
  from_status: DatasetStatus | null
  to_status: DatasetStatus
  actor_id: string | null
  note: string | null
  blockers: string[]
  at: string
}

export interface DatasetItem {
  id: string
  name: string
  version: string
  kind: 'real' | 'synthetic'
  source_url: string
  accessed_at: string | null
  licence_spdx: string
  images_licence_spdx: string
  annotations_licence_spdx: string | null
  has_annotations: boolean
  image_origin: ImageOrigin
  attribution_required: boolean | null
  attribution_text: string | null
  commercial_use: Tri
  redistribution: Tri
  intended_use: string
  notes: string | null
  status: DatasetStatus
  created_by: string | null
  created_at: string
  approved_by: string | null
  approved_at: string | null
  licence_verdict: string
  blockers: string[]
  download_allowed: boolean
  is_biological_data: boolean
}

export interface DatasetDetailRecord extends DatasetItem {
  evidence: DatasetEvidenceRecord[]
  history: DatasetHistoryEntry[]
  sample_count: number
}

export interface DatasetSampleRecord {
  id: string
  external_id: string
  group_key: string | null
  label: string | null
  label_status: LabelStatus
  content_sha256: string | null
  phash: string | null
  file_status: 'ok' | 'invalid' | null
  width: number | null
  height: number | null
  provenance: Record<string, unknown>
  is_synthetic: boolean
  version: number
}

export interface LabelReviewRecord {
  id: string
  sample_id: string
  reviewer_id: string
  reviewer_qualification: string | null
  qualification_verified: boolean
  from_status: LabelStatus
  to_status: LabelStatus
  from_label: string | null
  to_label: string | null
  evidence: string | null
  at: string
}

export interface ReviewSummary {
  by_status: Record<string, number>
  reviewed_fraction: number
  qualified_reviewers_verified: number
  note: string
}

export interface QualityIssue { code: string; severity: 'error' | 'warning' | 'info'; message: string; count: number; examples: string[] }
export interface QualityReport {
  samples: number
  passed: boolean
  issues: QualityIssue[]
  label_status?: Record<string, number>
  reviewed_fraction?: number
  classes?: { classes?: number; counts?: Record<string, number>; max_over_min?: number; normalised_entropy?: number }
  groups?: { count: number; largest: number }
}

export interface AgreementReport {
  samples_with_a_decision: number
  samples_with_two_reviewers: number
  reviewers: number
  observed_agreement: number | null
  cohens_kappa: number | null
  disagreements: { sample_id: string; external_id?: string | null; verdicts: string[] }[]
  caveats: string[]
}

export interface SplitRecord {
  id: string
  version: number
  seed: number
  fractions: Record<string, number>
  include_unreviewed: boolean
  manifest_sha256: string
  stats: Record<string, { items: number; target_fraction: number; actual_fraction: number; groups: number; labels: Record<string, number> }>
  warnings: string[]
  leakage_violations: Record<string, unknown>[]
  created_by: string | null
  created_at: string
}

export interface ClaimReadiness {
  allowed: boolean
  blockers: { code: string; message: string; resolvable_in_application: boolean }[]
  split_version: number | null
  note: string
}

export interface LicencePolicy {
  eligible: string[]
  excluded: string[]
  not_covered: string
  override: string
  status: string
  approval_requires: string[]
  download_rule: string
}

// ------------------------------------------------------------------ evaluation protocols (Stage D3)
export type ProtocolRole = 'plant_pathologist' | 'data_owner' | 'independent_evaluator'
export interface ProtocolStatus { state: string; blockers: string[]; signed_roles: string[] }
export interface ProtocolSummaryRecord {
  id: string; key: string; version: number; title: string; content_sha256: string
  created_by: string | null; created_at: string; status: ProtocolStatus; is_proposal_only: boolean
}
export interface ProtocolThreshold {
  id: string; metric: string; scope: string; comparator: 'ge' | 'le' | 'gt' | 'lt'; value: number | null
  basis: string; requires_domain_expertise: boolean; status: 'proposed' | 'pending_domain_approval'; justification: string
}
export interface ProtocolContentRecord {
  title: string; intended_use: string; not_for: string[]; target_population: string; species: string[]; disease_classes: string[]
  inclusion_criteria: string[]; exclusion_criteria: string[]; dataset_requirements: string[]; label_requirements: string[]
  grouping: { hierarchy: string[]; test_split_unit: string; claim_downgrade_if_no_site: string }
  methodology: string[]; baselines: string[]; metrics: string[]; confidence_and_calibration: string[]
  error_costs: { false_negative: string; false_positive: string; operating_point: string }
  thresholds: ProtocolThreshold[]; required_signoffs: ProtocolRole[]; prohibited_claims: string[]; limitations: string[]
}
export interface ProtocolSignoffRecord {
  id: string; role: ProtocolRole; decision: 'approve' | 'reject'; signer_id: string
  declared_qualification: string | null; qualification_verified: boolean; note: string; at: string
}
export interface ProtocolDetailRecord extends ProtocolSummaryRecord { content: ProtocolContentRecord; signoffs: ProtocolSignoffRecord[] }
export interface ProtocolTemplate { content: ProtocolContentRecord; note: string; required_roles: ProtocolRole[] }

export interface ImportIssue { row: number | null; external_id?: string | null; column?: string; code: string; message: string }
export interface ImportWarning { code: string; message: string; count: number; rows: number[] }
export interface ImportReport {
  status: 'preview' | 'imported' | 'already_imported'
  ok: boolean
  csv_sha256: string
  columns: string[]
  rows_total: number
  rows_with_errors: number
  to_create: number
  unchanged: number
  error_count: number
  errors: ImportIssue[]
  errors_truncated: boolean
  warnings: ImportWarning[]
  label_status_after_import: 'unreviewed'
  note: string
}

// ------------------------------------------------------------------ asset lifecycle (ADR-055)
export interface StageChoice { key: string; label: string; kind: 'stage' | 'exit'; manager_only: boolean }
export interface LifecycleTemplate {
  mode: string
  stages: StageChoice[]
  exits_individual: StageChoice[]
  exits_population: StageChoice[]
  rules: string[]
}
export interface LifecycleEvent {
  id: string
  asset_id: string
  stage: string
  stage_label: string
  previous_stage: string | null
  entered_at: string
  recorded_at: string
  source: 'manual' | 'system'
  correction: boolean
  note: string | null
  actor_id: string | null
}
export interface AssetLifecycle {
  asset_id: string
  current_stage: string
  is_active: boolean
  next_choices: StageChoice[]
  history: LifecycleEvent[]
}

// ------------------------------------------------------------------ harvest records (ADR-056)
export type HarvestUnit = 'kg' | 't' | 'count' | 'l'
export interface HarvestRecord {
  id: string
  asset_id: string
  harvested_at: string
  quantity: number
  unit: HarvestUnit
  grade: string | null
  note: string | null
  supersedes_id: string | null
  superseded_by: string | null
  effective: boolean
  withdrawn: boolean
  recorded_by: string | null
  recorded_at: string
}
export interface HarvestPeriodTotals {
  by_unit: Record<string, number>
  mass_tonnes: number
  records: number
}
export interface HarvestOverview {
  since: string
  until: string
  totals: HarvestPeriodTotals
  by_month: (HarvestPeriodTotals & { month: string })[]
  by_asset: (HarvestPeriodTotals & { asset_id: string; asset_label: string })[]
  records: (HarvestRecord & { asset_label: string })[]
  truncated: boolean
}
export interface AssetHarvests {
  asset_id: string
  totals: { by_unit: Record<string, number>; mass_tonnes: number; records: number }
  history: HarvestRecord[]
}

// ------------------------------------------------------------------ actions and verification (ADR-059)
export type ActionKind = 'treat' | 'water' | 'fertilize' | 'prune' | 'pest_control' | 'weed' | 'mulch' | 'replant' | 'other'
export type ActionUnit = 'l' | 'ml' | 'kg' | 'g' | 'count'
export interface ActionRecord {
  id: string
  asset_id: string
  issue_id: string | null
  issue_key: string | null
  task_id: string | null
  task_key: string | null
  kind: ActionKind
  product: string | null
  quantity: number | null
  unit: ActionUnit | null
  performed_at: string
  performed_by: string | null
  note: string | null
  follow_up_task_id: string | null
  follow_up_task_key: string | null
  supersedes_id: string | null
  superseded_by: string | null
  effective: boolean
  withdrawn: boolean
  recorded_by: string | null
  recorded_at: string
}
export interface AssetActions {
  asset_id: string
  history: ActionRecord[]
}
export type VerificationStatus = 'not_applicable' | 'awaiting_follow_up' | 'improved' | 'unchanged' | 'worse' | 'observed_without_score'
export interface Verification {
  status: VerificationStatus
  method: 'rule'
  min_change: number
  actions: number
  last_action_at: string | null
  baseline_score: number | null
  baseline_at: string | null
  follow_up_score: number | null
  follow_up_at: string | null
  change: number | null
  required_for_success: boolean
}

// ------------------------------------------------------------------ recurring inspections (ADR-062)
export type ScheduleOutcome = 'created' | 'skipped_open_task' | 'skipped_inactive_asset'
export interface ScheduleOccurrence {
  due_at: string
  outcome: ScheduleOutcome
  task_id: string | null
  task_key: string | null
  task_status: string | null
  missed: number
  created_at: string
}
export interface InspectionSchedule {
  id: string
  asset_id: string | null
  asset_label: string | null
  location_id: string | null
  location_name: string | null
  title: string
  task_type: 'inspect' | 'monitor'
  interval_days: number
  lead_days: number
  next_due_at: string
  assignee_id: string | null
  priority: string
  active: boolean
  created_by: string | null
  created_at: string
  updated_at: string
  version: number
}
export interface ScheduleDetail extends InspectionSchedule {
  occurrences: ScheduleOccurrence[]
}
export interface GenerateResult {
  due: number
  created: number
  skipped_open_task: number
  skipped_inactive_asset: number
  task_keys: string[]
}
