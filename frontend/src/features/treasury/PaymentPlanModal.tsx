import { useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Button, Input, LoadingState, Modal, Table, type TableColumn } from '../../design-system'
import { useMutationError } from '../../hooks/useMutationError'
import {
  apService,
  type PaymentPlanItem,
  type PaymentPlanItemInput,
  type SupplierInvoice,
} from '../../services/apArService'
import { formatMoney } from '../../utils/currency'
import { distributeMonthlyCents } from '../../utils/paymentScheduleUtils'

interface DraftRow {
  dueDate: string
  amount: string
}

function toCents(value: string | number): bigint {
  const raw = typeof value === 'number' ? value.toFixed(2) : value.trim()
  const [whole, fraction = ''] = raw.split('.')
  return BigInt(whole || '0') * 100n + BigInt(fraction.padEnd(2, '0').slice(0, 2))
}

function fromCents(value: bigint): string {
  return `${value / 100n}.${String(value % 100n).padStart(2, '0')}`
}

/**
 * Calendario previsto de flujo de caja de una factura AP no contractual.
 * No ejecuta pagos ni sustituye ContractPaymentSchedule.
 */
export function PaymentPlanModal({
  invoice,
  onClose,
  onSaved,
}: {
  invoice: SupplierInvoice
  onClose: () => void
  onSaved: () => void
}) {
  const handleMutationError = useMutationError()
  const totalCents = toCents(invoice.amount) + toCents(invoice.taxAmount ?? 0)

  const planQuery = useQuery({
    queryKey: ['ap', 'payment-plan', invoice.id],
    queryFn: () => apService.getPaymentPlan(invoice.id),
  })

  const [rows, setRows] = useState<DraftRow[] | null>(null)
  const [regularMonths, setRegularMonths] = useState('7')
  const [firstMonth, setFirstMonth] = useState(invoice.dueDate?.slice(0, 7) ?? '')
  const [dueDay, setDueDay] = useState(String(Number(invoice.dueDate?.slice(8, 10)) || 1))
  const canGenerate = Number.isInteger(Number(regularMonths)) && Number(regularMonths) >= 1 &&
    Number(regularMonths) <= 36 && Number.isInteger(Number(dueDay)) &&
    Number(dueDay) >= 1 && Number(dueDay) <= 31 && firstMonth.length === 7 &&
    totalCents >= BigInt(Number(regularMonths))
  const draft: DraftRow[] = useMemo(() => {
    if (rows) return rows
    if (planQuery.data && planQuery.data.length > 0) {
      return planQuery.data.map((item) => ({ dueDate: item.dueDate, amount: String(item.amount) }))
    }
    return [{ dueDate: '', amount: '' }]
  }, [rows, planQuery.data])

  const draftTotalCents = draft.reduce((acc, row) => {
    try { return acc + toCents(row.amount) } catch { return acc }
  }, 0n)
  const balanced = draftTotalCents === totalCents
  const editable = ['APPROVED', 'SCHEDULED'].includes(invoice.status) && toCents(invoice.amountPaid ?? '0') === 0n

  const save = useMutation({
    mutationFn: () =>
      apService.setPaymentPlan(
        invoice.id,
        draft.map<PaymentPlanItemInput>((row) => ({
          dueDate: row.dueDate,
          amount: fromCents(toCents(row.amount)),
        })),
      ),
    onSuccess: () => {
      onSaved()
      onClose()
    },
    onError: (error) => handleMutationError(error, 'Guardar plan de pago'),
  })

  const columns: TableColumn<PaymentPlanItem>[] = [
    { key: 'sequence', header: '#', render: (row) => row.sequence },
    { key: 'dueDate', header: 'Vence', render: (row) => row.dueDate },
    { key: 'amount', header: 'Monto', render: (row) => formatMoney(row.amount, invoice.currencyCode) },
  ]

  return (
    <Modal open title={`Calendario previsto · ${invoice.invoiceNumber}`} onClose={onClose}>
      <p className="nx-field__hint">
        Forecast informativo: total de la factura <strong>{formatMoney(fromCents(totalCents), invoice.currencyCode)}</strong>.
        Este calendario no autoriza ni asigna pagos.
      </p>

      {planQuery.isLoading ? (
        <LoadingState label="Cargando plan…" />
      ) : planQuery.data && planQuery.data.length > 0 ? (
        <Table
          columns={columns}
          rows={planQuery.data}
          getRowKey={(row) => row.id}
          emptyMessage="Sin cuotas"
        />
      ) : null}

      {editable ? (
        <div className="nx-treasury__form" style={{ marginTop: '0.75rem' }}>
          <p className="nx-field__hint">Simula un calendario mensual antes de guardarlo. El último vencimiento recibe los centavos de ajuste; no se realizan pagos.</p>
          <div className="nx-treasury__actions">
            <Input label="Número de cuotas mensuales" type="number" min={1} max={36} value={regularMonths}
              onChange={event => setRegularMonths(event.target.value)} />
            <Input label="Primer mes (AAAA-MM)" type="month" value={firstMonth}
              onChange={event => setFirstMonth(event.target.value)} />
            <Input label="Día de pago (1–31)" type="number" min={1} max={31} value={dueDay}
              onChange={event => setDueDay(event.target.value)} />
          </div>
          <Button variant="secondary" disabled={!canGenerate} onClick={() => {
            const plan = distributeMonthlyCents(totalCents, Number(regularMonths), firstMonth, Number(dueDay))
            setRows(plan.map(item => ({ dueDate: item.dueDate, amount: fromCents(item.amountCents) })))
          }}>
            Calcular y previsualizar cuotas
          </Button>
          <p className="nx-field__hint">Para un día 29, 30 o 31 inexistente en un mes, se utilizará el último día de ese mes.</p>
          {draft.map((row, index) => (
            <div key={index} className="nx-treasury__actions">
              <Input
                label={`Cuota ${index + 1} · vencimiento`}
                type="date"
                value={row.dueDate}
                onChange={(event) => {
                  const next = [...draft]
                  next[index] = { ...next[index], dueDate: event.target.value }
                  setRows(next)
                }}
              />
              <Input
                label="Monto"
                type="number"
                value={row.amount}
                onChange={(event) => {
                  const next = [...draft]
                  next[index] = { ...next[index], amount: event.target.value }
                  setRows(next)
                }}
              />
              {draft.length > 1 ? (
                <Button
                  variant="secondary"
                  onClick={() => setRows(draft.filter((_, i) => i !== index))}
                >
                  Quitar
                </Button>
              ) : null}
            </div>
          ))}
          <Button variant="secondary" onClick={() => setRows([...draft, { dueDate: '', amount: '' }])}>
            Añadir cuota
          </Button>
          <p className={balanced ? 'nx-field__hint' : 'nx-field__error'} role={balanced ? undefined : 'alert'}>
            Suma de cuotas: {formatMoney(fromCents(draftTotalCents), invoice.currencyCode)}{' '}
            {balanced ? '· coincide' : `· debe ser ${formatMoney(fromCents(totalCents), invoice.currencyCode)}`}
          </p>
          <Button
            loading={save.isPending}
            disabled={!balanced || draft.some((row) => !row.dueDate || !row.amount)}
            onClick={() => save.mutate()}
          >
            Guardar calendario previsto
          </Button>
        </div>
      ) : (
        <p className="nx-field__hint">
          El plan solo puede editarse mientras la factura está aprobada o programada y sin pagos aplicados.
        </p>
      )}
    </Modal>
  )
}
