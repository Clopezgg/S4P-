import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Badge, Button, Card, EmptyState, LoadingState, Select, Table, type TableColumn } from '../../design-system'
import { apService, type PaymentProposalItem, type SupplierInvoice } from '../../services/apArService'
import { treasuryService } from '../../services/treasuryService'
import { formatMoney } from '../../utils/currency'
import { daysUntilBusinessDate } from '../../utils/dueDateUtils'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { useAuth } from '../auth/auth-context'
import { PaySupplierInvoiceButton } from './SupplierInvoiceFlows'
import { AccountsPayablePage } from './AccountsPayablePage'
import { PaymentPlanModal } from './PaymentPlanModal'
import { SupplierPaymentHistoryModal } from './SupplierPaymentHistoryModal'

export function AccountsPayableWorkspace() {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const canPay = Boolean(user?.permissions?.includes('ap.supplier_payment:create'))
  const [invoiceId, setInvoiceId] = useState('')
  const [horizonDays, setHorizonDays] = useState(14)
  const [historyInvoice, setHistoryInvoice] = useState<SupplierInvoice | null>(null)
  const [planInvoice, setPlanInvoice] = useState<SupplierInvoice | null>(null)

  const { companies, activeCompany, activeCompanyId: selectedCompanyId, setActiveCompanyId, isLoading: companiesLoading } = useActiveCompany()
  const activeCompanyId = selectedCompanyId ?? ''
  const currencyCode = activeCompany?.functionalCurrencyCode ?? null

  const invoicesQuery = useQuery({
    queryKey: ['ap', 'supplier-invoices', activeCompanyId],
    queryFn: () => apService.listInvoices(activeCompanyId),
    enabled: Boolean(activeCompanyId),
  })
  const treasuryQuery = useQuery({
    queryKey: ['treasury', 'accounts', activeCompanyId],
    queryFn: () => treasuryService.listAccounts(activeCompanyId),
    enabled: Boolean(activeCompanyId),
  })
  const invoices = invoicesQuery.data ?? []
  const selectedInvoice = invoices.find((invoice) => invoice.id === invoiceId) ?? null

  const proposalQuery = useQuery({
    queryKey: ['ap', 'payment-proposal', activeCompanyId, horizonDays],
    queryFn: () => apService.paymentProposal(activeCompanyId, horizonDays),
    enabled: Boolean(activeCompanyId),
  })
  const proposalColumns: TableColumn<PaymentProposalItem>[] = [
    { key: 'invoice', header: 'Factura', render: (row) => row.invoiceNumber },
    { key: 'supplier', header: 'Proveedor', render: (row) => row.supplierName ?? '—' },
    { key: 'due', header: 'Vence', render: (row) => row.dueDate },
    { key: 'countdown', header: 'Plazo', render: (row) => {
      const days = daysUntilBusinessDate(row.dueDate)
      return days === null ? '—' : days < 0 ? 'Vencida hace ' + (-days) + ' días' : days === 0 ? 'Vence hoy' : 'En ' + days + ' días'
    } },
    { key: 'remaining', header: 'A pagar', render: (row) => formatMoney(row.remaining, currencyCode) },
    { key: 'actions', header: 'Acciones', render: row => {
      const invoice = invoices.find(item => item.id === row.invoiceId)
      return invoice ? <div className="nx-treasury__actions">
        {canPay && ['APPROVED', 'SCHEDULED', 'PARTIALLY_PAID'].includes(invoice.status) && treasuryQuery.data?.length ?
          <PaySupplierInvoiceButton
            invoice={invoice}
            companyId={activeCompanyId}
            treasuryAccounts={treasuryQuery.data}
            remaining={invoice.amount + invoice.taxAmount - invoice.amountPaid}
            selectedInstallmentId={invoice.contractInstallmentId}
            label="Pagar cuota o saldo"
          /> : null}
        <Button variant="secondary" onClick={() => setPlanInvoice(invoice)}>Ver calendario</Button>
        <Button variant="secondary" onClick={() => setHistoryInvoice(invoice)}>Ver pagos</Button>
      </div> : null
    } },
    {
      key: 'flag',
      header: '',
      render: (row) => (row.overdue ? <Badge tone="danger">Vencida</Badge> : null),
    },
  ]

  if (companiesLoading) return <LoadingState label="Cargando cuentas por pagar…" />

  return (
    <div className="nx-treasury">
      <AccountsPayablePage />

      <Card title="Propuesta de pagos y vencimientos">
        <Select label="Ver obligaciones de los próximos" value={String(horizonDays)} onChange={event => setHorizonDays(Number(event.target.value))}>
          <option value="7">7 días</option>
          <option value="14">14 días</option>
          <option value="30">30 días</option>
          <option value="60">60 días</option>
        </Select>
        {companies.length === 0 ? (
          <EmptyState icon="card" title="No hay compañía configurada" description="Configura una compañía." />
        ) : proposalQuery.isLoading ? (
          <LoadingState label="Calculando propuesta de pago…" />
        ) : proposalQuery.data?.items ? (
          <>
            <div className="nx-treasury__actions">
              <Badge>
                {proposalQuery.data.items.length} factura(s) · total{' '}
                {formatMoney(proposalQuery.data.total ?? '0', currencyCode)}
              </Badge>
            </div>
            <Table
              columns={proposalColumns}
              rows={proposalQuery.data.items}
              getRowKey={(row) => row.invoiceId}
              emptyMessage="Nada por pagar en el horizonte."
            />
          </>
        ) : null}
      </Card>

      <Card title="Historial formal de pagos y reversals">
        {companies.length === 0 ? (
          <EmptyState
            icon="card"
            title="No hay compañía configurada"
            description="Configura una compañía antes de consultar pagos."
          />
        ) : (
          <div className="nx-treasury__form">
            <p className="nx-field__hint">
              Los pagos contabilizados nunca se eliminan. Un reversal crea un asiento inverso y conserva motivo, usuario, fecha y documento origen.
            </p>
            <Select
              label="Compañía"
              value={activeCompanyId}
              onChange={(event) => {
                setActiveCompanyId(event.target.value)
                setInvoiceId('')
              }}
            >
              {companies.map((company) => (
                <option key={company.id} value={company.id}>{company.name}</option>
              ))}
            </Select>
            <Select
              label="Factura de proveedor"
              value={invoiceId}
              onChange={(event) => setInvoiceId(event.target.value)}
              disabled={invoicesQuery.isLoading}
            >
              <option value="">Selecciona una factura…</option>
              {invoices.map((invoice) => (
                <option key={invoice.id} value={invoice.id}>
                  {invoice.invoiceNumber} — {formatMoney(invoice.amount, invoice.currencyCode)} — {invoice.status}
                </option>
              ))}
            </Select>
            <div className="nx-treasury__actions">
              {canPay && selectedInvoice && ['APPROVED', 'SCHEDULED', 'PARTIALLY_PAID'].includes(selectedInvoice.status) ?
                <PaySupplierInvoiceButton
                  invoice={selectedInvoice}
                  companyId={activeCompanyId}
                  treasuryAccounts={treasuryQuery.data ?? []}
                  remaining={selectedInvoice.amount + selectedInvoice.taxAmount - selectedInvoice.amountPaid}
                  selectedInstallmentId={selectedInvoice.contractInstallmentId}
                  label="Registrar pago parcial o total"
                /> : null}
              <Button
                variant="secondary"
                disabled={!selectedInvoice}
                onClick={() => selectedInvoice && setHistoryInvoice(selectedInvoice)}
              >
                Ver pagos y anulaciones
              </Button>
              <Button
                variant="secondary"
                disabled={!selectedInvoice}
                onClick={() => selectedInvoice && setPlanInvoice(selectedInvoice)}
              >
                Calendario previsto (forecast)
              </Button>
            </div>
          </div>
        )}
      </Card>

      {planInvoice ? (
        <PaymentPlanModal
          invoice={planInvoice}
          onClose={() => setPlanInvoice(null)}
          onSaved={() => {
            queryClient.invalidateQueries({ queryKey: ['ap', 'supplier-invoices', activeCompanyId] })
            queryClient.invalidateQueries({ queryKey: ['ap', 'payment-plan', planInvoice.id] })
          }}
        />
      ) : null}

      {historyInvoice ? (
        <SupplierPaymentHistoryModal
          invoice={historyInvoice}
          treasuryAccounts={treasuryQuery.data ?? []}
          onClose={() => setHistoryInvoice(null)}
          onReversed={() => {
            queryClient.invalidateQueries({ queryKey: ['ap', 'supplier-invoices', activeCompanyId] })
            queryClient.invalidateQueries({ queryKey: ['ap', 'supplier-payments', historyInvoice.id] })
            queryClient.invalidateQueries({ queryKey: ['treasury', 'accounts', activeCompanyId] })
          }}
        />
      ) : null}
    </div>
  )
}
