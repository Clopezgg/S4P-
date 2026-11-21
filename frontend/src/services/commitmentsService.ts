import { apiFetch } from './httpClient'

export interface CommitmentLine {
  id: string
  source: 'AP' | 'CONTRACT' | 'MANUAL'
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
  planId: string | null
  accountingStatus: 'ERP' | 'UNPOSTED_MANUAL'
  scope: 'PERSONAL' | 'BUSINESS' | 'THIRD_PARTY'
  daysUntilDue: number
  alertNow: boolean
}

export interface CommitmentsOverview {
  asOf: string
  lines: CommitmentLine[]
  pendingByCurrency: Record<string, string>
  overdueByCurrency: Record<string, string>
  pendingByScope: Record<string, Record<string, string>>
  overdueByScope: Record<string, Record<string, string>>
}

export interface ObligationPlan {
  id: string
  title: string
  payee: string | null
  category: string
  scope: string
  currencyCode: string
  amount: string
  recurrence: 'ONCE' | 'MONTHLY'
  firstDueDate: string
  dueDay: number
  lastDueDate: string | null
  status: 'ACTIVE' | 'PAUSED' | 'CANCELLED'
}

export interface ObligationPlanInput {
  companyId: string
  title: string
  payee?: string
  category: string
  scope: string
  currencyCode: string
  amount: string
  recurrence: 'ONCE' | 'MONTHLY'
  firstDueDate: string
  dueDay: number
  lastDueDate?: string | null
}

export interface ManualSettlementInput {
  occurrenceDueDate: string
  paymentDate: string
  amount: string
  reference: string
}

export const commitmentsService = {
  overview: (companyId: string, horizonDays = 90, signal?: AbortSignal) =>
    apiFetch<CommitmentsOverview>(
      `/commitments/overview?companyId=${encodeURIComponent(companyId)}&horizon_days=${horizonDays}`,
      { signal },
    ),
  plans: (companyId: string) =>
    apiFetch<ObligationPlan[]>(`/obligation-plans?companyId=${encodeURIComponent(companyId)}`),
  createPlan: (payload: ObligationPlanInput) =>
    apiFetch<ObligationPlan>('/obligation-plans', { method: 'POST', body: JSON.stringify(payload) }),
  setPlanStatus: (id: string, status: ObligationPlan['status']) =>
    apiFetch<ObligationPlan>(`/obligation-plans/${encodeURIComponent(id)}/status?status=${status}`, { method: 'PATCH' }),
  recordExternalSettlement: (id: string, payload: ManualSettlementInput) =>
    apiFetch<unknown>(`/obligation-plans/${encodeURIComponent(id)}/settlements`, {
      method: 'POST', body: JSON.stringify(payload),
    }),
}
