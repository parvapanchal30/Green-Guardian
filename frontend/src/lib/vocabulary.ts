import type { WorkspaceMode } from '../api/types'

/** Mode changes words and emphasis, never the data model (ADR-006). */
export interface Vocabulary {
  modeLabel: string
  location: string
  locations: string
  primaryAsset: string
  kpis: string[]
  lifecycle: string[]
  audience: string
}

export const VOCABULARY: Record<WorkspaceMode, Vocabulary> = {
  green_management: {
    modeLabel: 'Green Management',
    location: 'Zone',
    locations: 'Zones',
    primaryAsset: 'Tree',
    kpis: ['Survival', 'Health', 'Growth', 'Canopy', 'Coverage'],
    lifecycle: ['Planted', 'Growing', 'Mature', 'Maintained', 'Health monitoring', 'Survival'],
    audience: 'Urban trees, parks, campuses, NGOs, afforestation, residential societies',
  },
  agricultural_production: {
    modeLabel: 'Agricultural Production',
    location: 'Field',
    locations: 'Fields',
    primaryAsset: 'Crop batch',
    kpis: ['Growth', 'Health', 'Yield', 'Harvest', 'Revenue'],
    lifecycle: ['Planted', 'Germination', 'Vegetative', 'Flowering', 'Fruiting', 'Harvest', 'Post-harvest'],
    audience: 'Farms, orchards, plantations, greenhouses, crop producers',
  },
}
