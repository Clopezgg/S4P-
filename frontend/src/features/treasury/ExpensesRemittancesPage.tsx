import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Card, EmptyState, ErrorState, LoadingState, Select } from '../../design-system'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { projectService } from '../../services/projectService'
import { useActiveContext } from '../context/useActiveContext'
import { ProjectWorkHome } from '../home/ProjectWorkHome'

/** Entrada simple a los gastos y remesas de una obra, sin duplicar la contabilidad. */
export function ExpensesRemittancesPage() {
  const { activeCompanyId } = useActiveCompany()
  const { context, setActiveProject, isLoading: contextLoading } = useActiveContext()
  const projectsQuery = useQuery({
    queryKey: ['projects', activeCompanyId],
    queryFn: () => projectService.list(activeCompanyId as string),
    enabled: Boolean(activeCompanyId),
  })
  if (!activeCompanyId) return <EmptyState title="Selecciona una compañía" description="Selecciona la empresa para consultar sus obras, gastos y remesas." />
  if (contextLoading || projectsQuery.isLoading) return <LoadingState label="Cargando obras…" />
  if (projectsQuery.isError) return <ErrorState description="No se pudieron cargar las obras." onRetry={() => projectsQuery.refetch()} />

  const projects = (projectsQuery.data ?? []).filter(project => project.status !== 'ARCHIVED')
  const selectedId = projects.some(project => project.id === context.activeProjectId) ? context.activeProjectId : null

  return <div className="nx-home">
    <Card title="Gastos y remesas">
      <p>Selecciona una obra o trabajo. Los gastos se muestran separados por obra; las remesas identifican el origen del dinero, pero no se contabilizan automáticamente como ingresos.</p>
      <Select label="Obra o trabajo" value={selectedId ?? ''} onChange={event => setActiveProject(event.target.value || null)}>
        <option value="">Seleccionar obra…</option>
        {projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
      </Select>
      <p><Link to="/finanzas/tesoreria">Administrar caja, bancos y movimientos generales</Link></p>
    </Card>
    {selectedId ? <ProjectWorkHome key={selectedId} projectId={selectedId} /> :
      <EmptyState title="Elige una obra" description="Aquí podrás registrar gastos y remesas y consultar sus totales y movimientos, sin entrar a múltiples módulos." />}
  </div>
}
