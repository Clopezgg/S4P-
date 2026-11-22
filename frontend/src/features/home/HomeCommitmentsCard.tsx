import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { commitmentsService } from '../../services/commitmentsService'
import { formatMoney } from '../../utils/currency'

const dueLabel = (days: number) =>
  days < 0 ? `Atrasado ${Math.abs(days)} día(s)`
    : days === 0 ? 'Vence hoy'
      : `Faltan ${days} día(s)`

export function HomeCommitmentsCard({ companyId }: { companyId: string }) {
  const query = useQuery({
    queryKey: ['commitments', 'overview', companyId, 30],
    queryFn: ({ signal }) => commitmentsService.overview(companyId, 30, signal),
  })
  const lines = Array.isArray(query.data?.lines) ? query.data.lines : []
  const upcoming = lines.filter(item => item.alertNow).slice(0, 5)
  const overdue = lines.filter(item => item.daysUntilDue < 0).length

  return (
    <section className="nx-home-commitments" aria-label="Compromisos urgentes">
      <div className="nx-home-commitments__heading">
        <div>
          <h2>Compromisos y pendientes</h2>
          <p>Alertas de pagos reales y planes personales registrados</p>
        </div>
        <Link to="/inicio/compromisos">Ver todo</Link>
      </div>
      {query.isPending ? <p role="status">Buscando próximos vencimientos…</p>
        : query.isError ? (
          <p>No se pudieron consultar los vencimientos. <Link to="/inicio/compromisos">Abrir centro</Link></p>
        ) : (
          <>
            <div className="nx-home-commitments__count">
              <strong>{overdue} vencido(s)</strong>
              <span>{lines.length} obligaciones registradas para los próximos 30 días y anteriores abiertas</span>
            </div>
            {upcoming.length ? upcoming.map(item => (
              <div className="nx-home-commitments__row" key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{dueLabel(item.daysUntilDue)} · {item.scope === 'PERSONAL' ? 'Personal' : item.scope === 'THIRD_PARTY' ? 'Terceros' : 'Empresa'}</span>
                </div>
                <span className="nx-home-commitments__money">
                  {formatMoney(item.remaining, item.currencyCode)}
                </span>
              </div>
            )) : <p>Sin alertas de vencimiento para hoy o los próximos 7, 3 y 1 días.</p>}
          </>
        )}
    </section>
  )
}
