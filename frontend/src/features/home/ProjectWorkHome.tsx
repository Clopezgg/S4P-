import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { Button, Card, EmptyState, ErrorState, Input, LoadingState, Select, StatCard, Table } from '../../design-system'
import { projectService } from '../../services/projectService'
import { formatMoney } from '../../utils/currency'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { useAuth } from '../auth/auth-context'
import { useActiveContext } from '../context/useActiveContext'
import { ProjectTreasuryEntry } from '../treasury/TreasuryPage'

export function ProjectWorkHome({ projectId }: { projectId: string }) {
  const { user } = useAuth()
  const { activeCompanyId } = useActiveCompany()
  const { setActiveProject } = useActiveContext()
  const queryClient = useQueryClient()
  const [entry, setEntry] = useState<'expense' | 'remittance' | null>(null)
  const [search, setSearch] = useSearchParams()
  const requestedEntry = search.get('project') === projectId ? search.get('entry') : null
  const activeEntry = entry ?? (requestedEntry === 'expense' || requestedEntry === 'remittance' ? requestedEntry : null)
  const [workName, setWorkName] = useState('')
  const [offset, setOffset] = useState(0)
  const [parentId, setParentId] = useState<string | null>(null)
  const grants = new Set(user?.permissions ?? [])
  const project = useQuery({ queryKey: ['project', projectId], queryFn: () => projectService.get(projectId) })
  const spending = useQuery({ queryKey: ['project', projectId, 'spending', offset], queryFn: ({ signal }) => projectService.getSpending(projectId, signal, offset) })
  const projects = useQuery({ queryKey: ['projects', activeCompanyId], queryFn: () => projectService.list(activeCompanyId as string), enabled: Boolean(activeCompanyId) })
  const lifecycle = useQuery({ queryKey: ['project', projectId, 'lifecycle'], queryFn: () => projectService.getLifecycle(projectId) })
  function refresh() { queryClient.invalidateQueries({ queryKey: ['project'] }); queryClient.invalidateQueries({ queryKey: ['projects'] }) }
  const activate = useMutation({ mutationFn: () => projectService.transitionStatus(projectId, 'ACTIVE'), onSuccess: refresh })
  const createWork = useMutation({
    mutationFn: () => projectService.create({ companyId: project.data!.companyId, parentProjectId: projectId,
      name: workName.trim(), currencyCode: project.data!.currencyCode ?? spending.data!.currencyCode }),
    onSuccess: (created) => { refresh(); setWorkName(''); setActiveProject(created.id) },
  })
  const linkParent = useMutation({ mutationFn: () => projectService.update(projectId, { parentProjectId: parentId === null ? (project.data?.parentProjectId ?? null) : (parentId || null) }), onSuccess: refresh })
  if (project.isLoading || spending.isLoading) return <LoadingState label="Cargando gastos de la obra…" />
  if (!project.data || !spending.data || project.isError || spending.isError) return <ErrorState description="No se pudieron cargar los gastos del proyecto." onRetry={() => { project.refetch(); spending.refetch() }} />
  if (project.data.companyId !== activeCompanyId) return <EmptyState title="Selecciona un proyecto de la empresa activa" />
  const p = project.data
  const data = spending.data
  const needsAccounts = grants.has('treasury.account:read') && grants.has('accounting.account:read')
  const canActivate = grants.has('project:update') && lifecycle.data?.allowedTransitions.some(t => t.status === 'ACTIVE' && !t.sensitive)
  const currentParent = projects.data?.find(row => row.id === p.parentProjectId)
  const projectNames = new Map(data.projects.map(row => [row.id, row.name]))
  return <div className="nx-home">
    <header className="nx-home__header"><div>
      <p className="nx-home__eyebrow">{p.parentProjectId ? 'Trabajo de la obra' : 'Obra / proyecto'}</p>
      <h1 className="nx-dashboard__title">{p.name}</h1>
      <p className="nx-home__subtitle">{p.parentProjectId ? 'Solo los movimientos de este trabajo.' : 'Gastos directos y de los trabajos vinculados. Otros proyectos quedan fuera.'}</p>
      {currentParent ? <Button variant="secondary" onClick={() => setActiveProject(currentParent.id)}>Ver toda la obra: {currentParent.name}</Button> : null}
    </div></header>
    <div className="nx-work-actions">
      {grants.has('treasury.general_expense:create') && needsAccounts ? <Button disabled={p.status !== 'ACTIVE'} onClick={() => setEntry('expense')}>Registrar gasto</Button> : null}
      {grants.has('treasury.remittance:create') && needsAccounts ? <Button variant="secondary" onClick={() => setEntry('remittance')}>Registrar remesa</Button> : null}
      <a href="#gastos-de-la-obra">Todos los gastos</a>
    </div>
    {p.status !== 'ACTIVE' ? <p className="nx-field__hint">Para registrar gastos, el proyecto debe estar activo.</p> : null}
    {grants.has('treasury.general_expense:create') && !needsAccounts ? <p role="alert">Tu usuario necesita acceso de lectura a las cuentas pagadoras y al catálogo de cuentas para registrar gastos.</p> : null}
    {canActivate ? <Card title="Preparar el proyecto para operar"><p>El proyecto está {lifecycle.data?.currentStatusLabel.toLowerCase()}. Puedes activarlo sin configurar contratos ni fases WBS.</p><Button loading={activate.isPending} onClick={() => activate.mutate()}>Activar proyecto</Button>{activate.error ? <p role="alert">{activate.error.message}</p> : null}</Card> : null}
    <section className="nx-home__grid nx-work-summary" aria-label="Resumen de gastos de la obra">
      <StatCard label="Todos los gastos de esta obra" value={formatMoney(data.totalExpenses, data.currencyCode)} />
      <StatCard label="Remesas identificadas para esta obra" value={data.totalRemittances === null ? 'Sin permiso de consulta' : formatMoney(data.totalRemittances, data.currencyCode)} />
      <StatCard label="Trabajos vinculados" value={data.projects.filter(row => row.id !== projectId).length} />
    </section>
    <p className="nx-field__hint">Las remesas identifican aportes para la obra. El dinero disponible permanece en caja o banco y se consulta en Tesorería.</p>
    {data.scopeLimited ? <p className="nx-field__hint">El resumen incluye únicamente los proyectos y trabajos a los que tienes acceso.</p> : null}
    <Card title="Trabajos de esta obra">
      <p>Cada trabajo conserva su propio detalle. El total de la obra los suma una sola vez.</p>
      <Table rows={data.projects} getRowKey={row => row.id} columns={[
        { key: 'name', header: 'Proyecto / trabajo', render: row => row.id === projectId ? `${row.name} · gastos directos` : <button className="nx-link-button" onClick={() => setActiveProject(row.id)}>{row.name}</button> },
        { key: 'total', header: 'Gastos', numeric: true, render: row => formatMoney(row.totalExpenses, data.currencyCode) },
      ]} />
      {!p.parentProjectId && grants.has('project:create') ? <form className="nx-work-create" onSubmit={event => { event.preventDefault(); if (workName.trim()) createWork.mutate() }}>
        <Input label="Nuevo trabajo de esta obra" value={workName} maxLength={255} required onChange={event => setWorkName(event.target.value)} placeholder="Verjas, Cerco perimetral, Techo, Acabados…" />
        <Button type="submit" loading={createWork.isPending} disabled={!workName.trim()}>Añadir trabajo</Button>
        {createWork.error ? <p role="alert">{createWork.error.message}</p> : null}
      </form> : null}
    </Card>
    <div id="gastos-de-la-obra"><Card title="Todos los gastos">
      <p>Gastos contabilizados de esta obra y sus trabajos. Los reversos se muestran para conservar el historial.</p>
      {data.expenses.length ? <Table rows={data.expenses} getRowKey={row => row.id} columns={[
        { key: 'date', header: 'Fecha', render: row => row.effectiveDate },
        { key: 'work', header: 'Proyecto / trabajo', render: row => projectNames.get(row.projectId) ?? '—' },
        { key: 'description', header: 'Concepto', render: row => row.description || row.documentNumber },
        { key: 'amount', header: 'Importe', numeric: true, render: row => formatMoney(row.amount, data.currencyCode) },
        { key: 'status', header: 'Estado', render: row => row.status === 'REVERSED' ? 'Revertido' : 'Contabilizado' },
      ]} /> : <EmptyState title="Aún no hay gastos en esta obra" description="Registra el primer gasto con el botón de arriba. Los gastos de Otros no aparecen aquí." />}
      {data.expenseCount > 25 ? <div className="nx-work-actions"><p>Movimientos {offset + 1}–{offset + data.expenses.length} de {data.expenseCount}. El total incluye todos.</p>
        <Button variant="secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Anteriores</Button>
        <Button variant="secondary" disabled={offset + data.expenses.length >= data.expenseCount} onClick={() => setOffset(offset + 25)}>Siguientes</Button>
      </div> : null}
    </Card></div>
    <details><summary>Opciones avanzadas del proyecto</summary>
      <Link to={`/proyectos/${projectId}`}>Presupuesto, contratos, fases y detalle financiero</Link>
      {grants.has('project:update') && data.projects.length === 1 ? <form onSubmit={event => { event.preventDefault(); linkParent.mutate() }}>
        <Select label="Obra principal" value={parentId ?? p.parentProjectId ?? ''} onChange={event => setParentId(event.target.value)}>
          <option value="">Proyecto independiente · fuera de otras obras</option>
          {(projects.data ?? []).filter(row => row.id !== projectId && !row.parentProjectId).map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
        </Select>
        <p>Al vincularlo, sus gastos también aparecerán en el total de esa obra. Otros debe permanecer independiente.</p>
        <Button type="submit" loading={linkParent.isPending}>Guardar vínculo</Button>{linkParent.error ? <p role="alert">{linkParent.error.message}</p> : null}
      </form> : null}
    </details>
    {activeEntry ? <ProjectTreasuryEntry key={`${projectId}-${activeEntry}`} project={p} kind={activeEntry} onClose={() => {
      setEntry(null); const next = new URLSearchParams(search); next.delete('entry'); next.delete('project'); setSearch(next, { replace: true }); refresh()
    }} /> : null}
  </div>
}
