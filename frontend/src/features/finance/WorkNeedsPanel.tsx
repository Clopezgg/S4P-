import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { workNeedsService } from '../../services/workNeedsService'
import { friendlyApiMessage } from '../../services/httpClient'
import { formatMoney } from '../../utils/currency'

export function WorkNeedsPanel({ companyId }: { companyId: string }) {
  const query = useQuery({
    queryKey: ['work-needs', companyId],
    queryFn: ({ signal }) => workNeedsService.overview(companyId, signal),
  })
  return (
    <section className="s4p-commitments__panel" aria-label="Compras y mantenimientos pendientes">
      <h2>Qué falta comprar o resolver</h2>
      <p>Solicitudes de compra aún abiertas y trabajos de mantenimiento en proceso. Los importes son estimaciones o costos registrados, no saldos bancarios exigibles.</p>
      {query.isPending ? <p role="status">Consultando solicitudes y trabajos…</p> : query.isError ? (
        <p role="alert">{friendlyApiMessage(query.error)}</p>
      ) : (
        <div className="s4p-commitments__needs">
          <div>
            <h3>Materiales y compras pendientes ({query.data.materials.length})</h3>
            {query.data.materials.length ? query.data.materials.map(item => (
              <article className="s4p-commitments__need" key={item.id}>
                <strong>{item.description}</strong>
                <span>{item.quantity} unidades solicitadas · {item.requisitionNumber} · {item.status}</span>
                <span>Estimado: {item.currencyCode ? formatMoney(item.estimatedTotal, item.currencyCode) : 'Moneda sin configurar'}</span>
                {item.requiredDate && <span>Necesario el {item.requiredDate}</span>}
              </article>
            )) : <p>Sin solicitudes de compra pendientes.</p>}
            <Link to="/abastecimiento/solicitudes">Administrar compras</Link>
          </div>
          <div>
            <h3>Mantenimiento pendiente ({query.data.maintenance.length})</h3>
            {query.data.maintenance.length ? query.data.maintenance.map(item => (
              <article className="s4p-commitments__need" key={item.id}>
                <strong>{item.equipmentName}</strong>
                <span>{item.description || 'Orden de mantenimiento'} · {item.status}</span>
                <span>Repuestos: {item.currencyCode ? formatMoney(item.recordedPartsCost, item.currencyCode) : '—'}</span>
                <span>Mano de obra: {item.currencyCode ? formatMoney(item.recordedLaborCost, item.currencyCode) : '—'}</span>
              </article>
            )) : <p>Sin órdenes de mantenimiento abiertas.</p>}
            <Link to="/recursos/mantenimiento">Gestionar vehículos y equipos</Link>
          </div>
        </div>
      )}
    </section>
  )
}
