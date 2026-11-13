import { useNavigate } from 'react-router-dom'
import { Sheet, Icon, type IconName } from '../design-system'
import { useAuth } from '../features/auth/auth-context'
import { useActiveContext } from '../features/context/useActiveContext'

interface QuickCreateProps {
  open: boolean
  onClose: () => void
}

interface QuickAction {
  label: string
  icon: IconName
  to: string
  requiredAny: string[]
}

/** Quick Create (§10) — sólo acciones reales y funcionales, filtradas por
 * permisos. Cada una navega a la pantalla del módulo correspondiente. */
const ACTIONS: QuickAction[] = [
  { label: 'Nuevo comprobante PDF', icon: 'receipt', to: '/finanzas/comprobantes', requiredAny: ['treasury.voucher:read'] },
  { label: 'Registrar gasto', icon: 'card', to: '/finanzas/tesoreria', requiredAny: ['treasury.general_expense:create', 'treasury.account:read'] },
  { label: 'Registrar remesa', icon: 'bank', to: '/finanzas/tesoreria', requiredAny: ['treasury.remittance:create', 'treasury.account:read'] },
  { label: 'Nueva factura de proveedor', icon: 'file', to: '/finanzas/cuentas-por-pagar', requiredAny: ['ap.supplier_invoice:read'] },
  { label: 'Nuevo cobro', icon: 'receipt', to: '/comercial/cobros', requiredAny: ['ar.customer_receipt:read'] },
  { label: 'Nueva evidencia', icon: 'camera', to: '/control/evidencias', requiredAny: ['document.evidence:read'] },
  { label: 'Nuevo proyecto', icon: 'project', to: '/proyectos', requiredAny: ['project:read'] },
]

export function QuickCreate({ open, onClose }: QuickCreateProps) {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { context } = useActiveContext()
  const grants = new Set(user?.permissions ?? [])
  const actions = ACTIONS.filter((action) => {
    if (action.label === 'Registrar gasto' || action.label === 'Registrar remesa') return action.requiredAny.every(permission => grants.has(permission)) && grants.has('accounting.account:read')
    if (action.label === 'Nuevo proyecto') return grants.has('project:create')
    return action.requiredAny.some((permission) => grants.has(permission))
  })

  return (
    <Sheet open={open} title="Crear" onClose={onClose}>
      {actions.length === 0 ? (
        <p className="nx-field__hint">No tienes permisos para crear registros nuevos.</p>
      ) : (
        <ul className="nx-quick-create">
          {actions.map((action) => (
            <li key={action.label}>
              <button
                type="button"
                className="nx-quick-create__action"
                onClick={() => {
                  onClose()
                  const kind = action.label === 'Registrar gasto' ? 'expense' : action.label === 'Registrar remesa' ? 'remittance' : null
                  navigate(kind && context.activeProjectId ? `/inicio?entry=${kind}&project=${encodeURIComponent(context.activeProjectId)}` : action.to)
                }}
              >
                <span className="nx-quick-create__icon" aria-hidden="true">
                  <Icon name={action.icon} />
                </span>
                {action.label}{context.activeProjectId && ['Registrar gasto', 'Registrar remesa'].includes(action.label) ? ` · ${context.activeProjectName ?? 'proyecto seleccionado'}` : ''}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Sheet>
  )
}
