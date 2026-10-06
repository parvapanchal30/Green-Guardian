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
