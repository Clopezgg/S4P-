import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { commitmentsService, type CommitmentLine } from '../../services/commitmentsService'
import { friendlyApiMessage } from '../../services/httpClient'
import { ObligationPlansPanel } from './ObligationPlansPanel'
import { ManualSettlementForm } from './ManualSettlementForm'
import { formatMoney } from '../../utils/currency'
import './CommitmentsCenterPage.css'

const dateLabel = (value: string) => {
  const [year, month, day] = value.split('-').map(Number)
  return new Intl.DateTimeFormat('es-HN', {
    day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, day)))
}

const categoryLabel = (row: CommitmentLine) => {
  if (row.source === 'CONTRACT') return 'Contrato / contratista'
  if (row.source === 'AP') return 'Proveedor'
  return ({ LAND: 'Terreno', CONTRACTOR: 'Contratista', MATERIAL: 'Materiales', VEHICLE: 'Vehículo', GENERAL: 'Gasto externo', OTHER: 'Otro' } as Record<string, string>)[row.category] ?? 'Compromiso manual'
}

const statusLabel: Record<string, string> = {
  OVERDUE: 'Vencido',
  DUE: 'Vence hoy',
  PARTIALLY_PAID: 'Pago parcial',
  UPCOMING: 'Programado',
}

export function CommitmentsCenterPage() {
  const { activeCompanyId, activeCompany } = useActiveCompany()
  const [filter, setFilter] = useState('ALL')
  const [search, setSearch] = useState('')
  const [selectedManualId, setSelectedManualId] = useState<string | null>(null)
  const [horizon, setHorizon] = useState(90)

  const query = useQuery({
    queryKey: ['commitments', 'overview', activeCompanyId, horizon],
    queryFn: ({ signal }) => commitmentsService.overview(activeCompanyId as string, horizon, signal),
    enabled: Boolean(activeCompanyId),
  })

  const lines = useMemo(() => (query.data?.lines ?? []).filter((line) => {
    if (filter === 'OVERDUE' && line.status !== 'OVERDUE') return false
    if (filter === 'AP' && line.source !== 'AP') return false
    if (filter === 'CONTRACT' && line.source !== 'CONTRACT') return false
    const term = search.trim().toLowerCase()
    return !term || `${line.title} ${line.payee ?? ''} ${line.category}`.toLowerCase().includes(term)
  }), [query.data, filter, search])

  const overdueCount = query.data?.lines.filter(line => line.status === 'OVERDUE').length ?? 0

  return (
    <main className="s4p-commitments">
      <div className="s4p-commitments__hero">
        <div>
          <p className="s4p-commitments__eyebrow">S4P 2.0 · Centro de control</p>
          <h1>Compromisos y pendientes</h1>
          <p>Vencimientos y saldos reales de facturas y cuotas de contratos, sin registros duplicados.</p>
          <p className="s4p-commitments__scope">{activeCompany?.name ?? 'Selecciona una empresa activa'}</p>
        </div>
        <Link className="s4p-commitments__action" to="/finanzas/libro-contractual">Administrar contratos</Link>
      </div>

      {!activeCompanyId ? (
        <div className="s4p-commitments__state">Selecciona una compañía para visualizar sus compromisos.</div>
      ) : query.isPending ? (
        <div className="s4p-commitments__state" role="status">Cargando obligaciones verificadas…</div>
      ) : query.isError ? (
        <div className="s4p-commitments__state" role="alert">
          <p>{friendlyApiMessage(query.error)}</p>
          <button type="button" onClick={() => query.refetch()}>Reintentar</button>
        </div>
      ) : (
        <>
          <div className="s4p-commitments__metrics">
            <article className="s4p-commitments__metric">
              <span>Obligaciones abiertas</span>
              <strong>{query.data.lines.length}</strong>
            </article>
            <article className="s4p-commitments__metric s4p-commitments__metric--urgent">
              <span>Vencidas</span>
              <strong>{overdueCount}</strong>
            </article>
            <article className="s4p-commitments__metric">
              <span>Por pagar · separado por moneda</span>
              {Object.entries(query.data.pendingByCurrency).length ? (
                Object.entries(query.data.pendingByCurrency).map(([currency, amount]) => (
                  <strong key={currency}>{formatMoney(amount, currency)}</strong>
                ))
              ) : <strong>Sin saldos abiertos</strong>}
            </article>
            <article className="s4p-commitments__metric">
              <span>Vencido · separado por moneda</span>
              {Object.entries(query.data.overdueByCurrency).length ? (
                Object.entries(query.data.overdueByCurrency).map(([currency, amount]) => (
                  <strong key={currency}>{formatMoney(amount, currency)}</strong>
                ))
              ) : <strong>Sin vencimientos</strong>}
            </article>
          </div>

          <section className="s4p-commitments__panel" aria-label="Lista de compromisos">
            <div className="s4p-commitments__toolbar">
              <div>
                <h2>Próximos pagos</h2>
                <p>Incluye obligaciones vencidas y las que vencerán en el período seleccionado.</p>
              </div>
              <label>Horizonte
                <select value={horizon} onChange={event => setHorizon(Number(event.target.value))}>
                  <option value={30}>30 días</option>
                  <option value={90}>90 días</option>
                  <option value={180}>180 días</option>
                  <option value={365}>365 días</option>
                </select>
              </label>
            </div>
            <div className="s4p-commitments__filters">
              <label className="s4p-commitments__search">Buscar
                <input type="search" placeholder="Contrato, proveedor o factura" value={search}
                  onChange={event => setSearch(event.target.value)} />
              </label>
              <div className="s4p-commitments__chips" aria-label="Filtrar compromisos">
                {[
                  ['ALL', 'Todos'], ['OVERDUE', 'Vencidos'],
                  ['CONTRACT', 'Contratos'], ['AP', 'Proveedores'],
                ].map(([value, label]) => (
                  <button type="button" key={value} aria-pressed={filter === value}
                    className={filter === value ? 'is-selected' : ''}
                    onClick={() => setFilter(value)}>{label}</button>
                ))}
              </div>
            </div>

            {lines.length ? (
              <div className="s4p-commitments__list">
                {lines.map(line => (
                  <article className="s4p-commitments__row" key={line.id}>
                    <div className="s4p-commitments__date">
                      <strong>{dateLabel(line.dueDate)}</strong>
                      <span className={line.status === 'OVERDUE' ? 'is-overdue' : ''}>
                        {statusLabel[line.status] ?? line.status}
                      </span>
                    </div>
                    <div className="s4p-commitments__description">
                      <strong>{line.title}</strong>
                      <span>{line.payee ?? categoryLabel(line)} · {categoryLabel(line)}</span>
                    </div>
                    <div className="s4p-commitments__money">
                      <strong>{formatMoney(line.remaining, line.currencyCode)}</strong>
                      {Number(line.paid) > 0 && <span>Abonado: {formatMoney(line.paid, line.currencyCode)}</span>}
                    </div>
                    {line.source === 'MANUAL' && line.planId ? (
                      <button type="button" onClick={() => setSelectedManualId(
                        selectedManualId === line.id ? null : line.id,
                      )}>Registrar abono</button>
                    ) : <Link to={line.detailUrl}>Ver detalle</Link>}
                    {selectedManualId === line.id && line.source === 'MANUAL' && activeCompanyId && (
                      <ManualSettlementForm key={line.id} line={line}
                        companyId={activeCompanyId} close={() => setSelectedManualId(null)} />
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <p className="s4p-commitments__empty">
                No hay obligaciones registradas con este filtro. No se generan cantidades ni cuotas de ejemplo.
              </p>
            )}
          </section>
        </>
      )}

      {activeCompanyId && <ObligationPlansPanel companyId={activeCompanyId} />}

      <section className="s4p-commitments__panel">
        <h2>Administrar otras necesidades</h2>
        <div className="s4p-commitments__shortcuts">
          <Link to="/abastecimiento/solicitudes">Materiales pendientes</Link>
          <Link to="/recursos/mantenimiento">Vehículos y mantenimiento</Link>
          <Link to="/operacion/movimientos">Gastos y remesas</Link>
          <Link to="/proyectos">Terrenos y obras como proyectos</Link>
        </div>
        <p className="s4p-commitments__disclaimer">
          Los saldos del ERP provienen de facturas y contratos; los compromisos manuales son
          planificación privada sin contabilización. Las alertas externas y conciliación automática
          con pagos reales siguen pendientes de certificación. Esta pantalla no realiza transferencias.
        </p>
      </section>
    </main>
  )
}
