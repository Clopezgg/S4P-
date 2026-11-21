import { apiFetch } from './httpClient'

export interface CommitmentLine {
  id: string
  source: 'AP' | 'CONTRACT'
  title: string
  payee: string | null
  category: string
  currencyCode: string
  dueDate: string
  amount: string
  paid: string
  remaining: string
  status: string
  detailUrl: string
}

export interface CommitmentsOverview {
  asOf: string
  lines: CommitmentLine[]
  pendingByCurrency: Record<string, string>
  overdueByCurrency: Record<string, string>
}

export const commitmentsService = {
  overview: (companyId: string, horizonDays = 90, signal?: AbortSignal) =>
    apiFetch<CommitmentsOverview>(
      `/commitments/overview?companyId=${encodeURIComponent(companyId)}&horizon_days=${horizonDays}`,
      { signal },
    ),
}
