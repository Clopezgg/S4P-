import { apiFetch } from './httpClient'

export interface MaterialNeed {
  id: string
  requisitionId: string
  requisitionNumber: string
  description: string
  quantity: string
  estimatedUnitCost: string
  estimatedTotal: string
  priority: string
  requiredDate: string | null
  currencyCode: string | null
  status: string
  projectId: string | null
}

export interface MaintenanceNeed {
  id: string
  equipmentId: string
  equipmentName: string
  description: string | null
  status: string
  openedAt: string
  recordedPartsCost: string
  recordedLaborCost: string
  currencyCode: string | null
}

export interface WorkNeeds {
  materials: MaterialNeed[]
  maintenance: MaintenanceNeed[]
}

export const workNeedsService = {
  overview: (companyId: string, signal?: AbortSignal) =>
    apiFetch<WorkNeeds>(
      `/work-needs/overview?companyId=${encodeURIComponent(companyId)}`,
      { signal },
    ),
}
