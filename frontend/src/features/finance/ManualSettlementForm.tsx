import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { commitmentsService, type CommitmentLine } from '../../services/commitmentsService'
import { friendlyApiMessage } from '../../services/httpClient'
import { formatMoney } from '../../utils/currency'

const localToday = () => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function ManualSettlementForm({
  line, companyId, close,
}: {
  line: CommitmentLine
  companyId: string
  close: () => void
}) {
  const qc = useQueryClient()
  const [amount, setAmount] = useState(line.remaining)
  const [paymentDate, setPaymentDate] = useState(localToday)
  const [reference, setReference] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: commitmentsService.recordExternalSettlement,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commitments', 'overview', companyId] })
      void qc.invalidateQueries({ queryKey: ['obligation-plans', companyId] })
      setMessage('Constancia de seguimiento registrada. No se generó movimiento bancario.')
    },
  })

  if (!line.planId || line.source !== 'MANUAL') return null

  return (
    <form className="s4p-commitments__settlement" onSubmit={event => {
      event.preventDefault()
      mutation.mutate({
        id: line.planId as string,
        payload: { occurrenceDueDate: line.dueDate, paymentDate, amount, reference: reference.trim() },
      })
    }}>
      <strong>Registrar un abono de seguimiento</strong>
      <p>{line.title} · cuota {line.dueDate} · saldo {formatMoney(line.remaining, line.currencyCode)}</p>
      <p className="s4p-commitments__disclaimer">Esta operación registra una constancia externa. NO ejecuta transferencias, NO disminuye saldos bancarios y NO publica asientos contables.</p>
      <label>Importe abonado
        <input required type="number" step="0.01" min="0.01" max={line.remaining}
          value={amount} onChange={e => setAmount(e.target.value)} />
      </label>
      <label>Fecha del pago
        <input required type="date" value={paymentDate} onChange={e => setPaymentDate(e.target.value)} />
      </label>
      <label>Referencia del comprobante
        <input required minLength={3} maxLength={160} value={reference}
          placeholder="Número de recibo, transferencia u otra referencia"
          onChange={e => setReference(e.target.value)} />
      </label>
      <div className="s4p-commitments__shortcuts">
        <button type="submit" disabled={mutation.isPending || Boolean(message)}>Guardar constancia</button>
        <button type="button" onClick={close}>Cerrar</button>
      </div>
      {mutation.isError && <p role="alert" className="s4p-commitments__error">{friendlyApiMessage(mutation.error)}</p>}
      {message && <p role="status" className="s4p-commitments__success">{message}</p>}
    </form>
  )
}
