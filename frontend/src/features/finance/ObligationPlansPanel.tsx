import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { commitmentsService, type ObligationPlan } from '../../services/commitmentsService'
import { friendlyApiMessage } from '../../services/httpClient'
import { formatMoney } from '../../utils/currency'

const now = new Date()
const initialMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
const initialDate = `${initialMonth}-${String(now.getDate()).padStart(2, '0')}`

const categoryLabels: Record<string, string> = {
  LAND: 'Terreno / inversión', CONTRACTOR: 'Contratista', MATERIAL: 'Materiales',
  VEHICLE: 'Vehículo', GENERAL: 'Gasto externo', OTHER: 'Otro',
}
const scopeLabels: Record<string, string> = {
  PERSONAL: 'Personal', BUSINESS: 'Empresarial (solo seguimiento)',
  THIRD_PARTY: 'Fondos de terceros (solo seguimiento)',
}

function firstDue(month: string, day: number): string {
  const [year, monthNum] = month.split('-').map(Number)
  const lastDay = new Date(Date.UTC(year, monthNum, 0)).getUTCDate()
  return `${month}-${String(Math.min(day, lastDay)).padStart(2, '0')}`
}

export function ObligationPlansPanel({ companyId }: { companyId: string }) {
  const qc = useQueryClient()
  const [title, setTitle] = useState('')
  const [payee, setPayee] = useState('')
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('LAND')
  const [scope, setScope] = useState('PERSONAL')
  const [currencyCode, setCurrency] = useState('HNL')
  const [recurrence, setRecurrence] = useState<'MONTHLY' | 'ONCE'>('MONTHLY')
  const [startMonth, setStartMonth] = useState(initialMonth)
  const [dueDay, setDueDay] = useState(15)
  const [singleDate, setSingleDate] = useState(initialDate)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<string | null>(null)

  const plansQuery = useQuery({
    queryKey: ['obligation-plans', companyId],
    queryFn: () => commitmentsService.plans(companyId),
  })
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ['obligation-plans', companyId] })
    void qc.invalidateQueries({ queryKey: ['commitments', 'overview', companyId] })
  }
  const create = useMutation({
    mutationFn: commitmentsService.createPlan,
    onSuccess: (plan) => {
      setSaved(`Compromiso "${plan.title}" guardado en seguimiento.`)
      setError(null)
      setTitle('')
      setPayee('')
      setAmount('')
      refresh()
    },
    onError: (err) => setError(friendlyApiMessage(err)),
  })
  const changeStatus = useMutation({
    mutationFn: ({ id, status }: { id: string, status: ObligationPlan['status'] }) =>
      commitmentsService.setPlanStatus(id, status),
    onSuccess: () => { setError(null); refresh() },
    onError: err => setError(friendlyApiMessage(err)),
  })

  return (
    <section className="s4p-commitments__panel" aria-label="Mis compromisos recurrentes">
      <h2>Mis compromisos personales y recurrentes</h2>
      <p>Terrenos (días 15 y 26), contratista (día 30), pagos externos, vehículos y otros compromisos. Introduce el importe real; nunca se generan cuotas monetarias de ejemplo.</p>
      <p className="s4p-commitments__disclaimer">Registros privados del usuario actual. Planificación y constancias externas solamente: NO generan automáticamente pagos, facturas, transferencias ni asientos contables.</p>
      <details>
        <summary className="s4p-commitments__disclosure">+ Crear compromiso recurrente o puntual</summary>
        <form className="s4p-commitments__form" onSubmit={event => {
          event.preventDefault()
          setSaved(null)
          setError(null)
          const firstDueDate = recurrence === 'MONTHLY' ? firstDue(startMonth, dueDay) : singleDate
          create.mutate({
            companyId, title: title.trim(), payee: payee.trim() || undefined,
            amount, category, scope, currencyCode: currencyCode.toUpperCase(),
            recurrence, firstDueDate,
            dueDay: recurrence === 'MONTHLY' ? dueDay : Number(singleDate.slice(-2)),
          })
        }}>
          <label>Concepto
            <input required minLength={2} maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="Ej. Cuota terreno 1" />
          </label>
          <label>A quién se paga
            <input maxLength={200} value={payee} onChange={e => setPayee(e.target.value)} placeholder="Beneficiario (opcional)" />
          </label>
          <label>Importe por vencimiento
            <input required type="number" min="0.01" step="0.01" value={amount} onChange={e => setAmount(e.target.value)} />
          </label>
          <label>Moneda
            <select value={currencyCode} onChange={e => setCurrency(e.target.value)}>
              <option value="HNL">HNL · Lempira</option>
              <option value="USD">USD · Dólar</option>
            </select>
          </label>
          <label>Categoría
            <select value={category} onChange={e => setCategory(e.target.value)}>
              {Object.entries(categoryLabels).map(([value, label]) =>
                <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Ámbito
            <select value={scope} onChange={e => setScope(e.target.value)}>
              {Object.entries(scopeLabels).map(([value, label]) =>
                <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label>Periodicidad
            <select value={recurrence} onChange={e => setRecurrence(e.target.value as 'MONTHLY' | 'ONCE')}>
              <option value="MONTHLY">Mensual</option>
              <option value="ONCE">Una sola vez</option>
            </select>
          </label>
          {recurrence === 'MONTHLY' ? (
            <>
              <label>Primer mes
                <input required type="month" value={startMonth} onChange={e => setStartMonth(e.target.value)} />
              </label>
              <label>Día de pago
                <input required type="number" min={1} max={31} value={dueDay} onChange={e => setDueDay(Number(e.target.value))} />
              </label>
              <p className="s4p-commitments__form-note">Primera cuota: {startMonth ? firstDue(startMonth, dueDay) : '—'}. Los meses sin el día seleccionado usarán su último día calendario.</p>
            </>
          ) : (
            <label>Fecha exacta de vencimiento
              <input required type="date" value={singleDate} onChange={e => setSingleDate(e.target.value)} />
            </label>
          )}
          <button type="submit" disabled={create.isPending}>Guardar compromiso</button>
        </form>
      </details>
      {error && <p role="alert" className="s4p-commitments__error">{error}</p>}
      {saved && <p role="status" className="s4p-commitments__success">{saved}</p>}
      <h3>Planes registrados</h3>
      {plansQuery.isPending ? <p>Cargando planes…</p> : plansQuery.isError ? (
        <p role="alert">{friendlyApiMessage(plansQuery.error)}</p>
      ) : plansQuery.data?.length ? (
        <div className="s4p-commitments__plans">
          {plansQuery.data.map(plan => (
            <div className="s4p-commitments__plan" key={plan.id}>
              <div>
                <strong>{plan.title}</strong>
                <p>{categoryLabels[plan.category] ?? plan.category} · {formatMoney(plan.amount, plan.currencyCode)} · {plan.recurrence === 'MONTHLY' ? `Día ${plan.dueDay} de cada mes` : plan.firstDueDate}</p>
                <small>{scopeLabels[plan.scope] ?? plan.scope} · {plan.status}</small>
              </div>
              <div className="s4p-commitments__chips">
                {plan.status === 'ACTIVE' && <button type="button" disabled={changeStatus.isPending}
                  onClick={() => changeStatus.mutate({ id: plan.id, status: 'PAUSED' })}>Pausar</button>}
                {plan.status === 'PAUSED' && <button type="button" disabled={changeStatus.isPending}
                  onClick={() => changeStatus.mutate({ id: plan.id, status: 'ACTIVE' })}>Reactivar</button>}
                {plan.status !== 'CANCELLED' && <button type="button" disabled={changeStatus.isPending}
                  onClick={() => {
                    if (window.confirm('¿Cancelar definitivamente el plan? Se conservará el historial.')) {
                      changeStatus.mutate({ id: plan.id, status: 'CANCELLED' })
                    }
                  }}>Cancelar</button>}
              </div>
            </div>
          ))}
        </div>
      ) : <p>Sin planes personales registrados. Agrega el primer compromiso con su importe real.</p>}
    </section>
  )
}
