import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FilterBar,
  Input,
  LoadingState,
  Select,
  Table,
  type TableColumn,
} from '../../design-system'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { crmService } from '../../services/crmService'
import { masterDataService } from '../../services/masterDataService'
import { procurementService } from '../../services/procurementService'
import { projectService } from '../../services/projectService'
import type { Project, ProjectStatus } from '../../types/project'
import { PROJECT_STATUS_LABELS, projectStatusLabel } from '../../utils/statusLabels'
import { useActiveContext } from '../context/useActiveContext'
import { ProjectWizard } from './ProjectWizard'
import { CompanyBootstrapForm } from '../settings/CompanyBootstrapForm'

const FILTERABLE_STATUSES: ProjectStatus[] = [
  'PLANNING', 'ACTIVE', 'ON_HOLD', 'COMPLETED', 'CLOSED', 'CANCELLED',
]

export function ProjectsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { context, setActiveProject } = useActiveContext()
  const { companies, activeCompany, activeCompanyId, isLoading: companiesLoading, isError: companiesError, refetch } = useActiveCompany()
  const [wizardOpen, setWizardOpen] = useState(false)
  const [quickCreateOpen, setQuickCreateOpen] = useState(false)
  const [quickProjectName, setQuickProjectName] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [filterText, setFilterText] = useState('')

  const effectiveStatus = showArchived && !filterStatus ? '' : filterStatus
  const projectsQuery = useQuery({
    queryKey: ['projects', activeCompanyId, effectiveStatus || (showArchived ? 'ALL' : 'DEFAULT')],
    queryFn: () => projectService.list(activeCompanyId as string, { status: effectiveStatus || undefined, includeArchived: showArchived }),
    enabled: Boolean(activeCompanyId),
  })
  const customersQuery = useQuery({
    queryKey: ['crm', 'customers', activeCompanyId],
    queryFn: () => crmService.listCustomers(activeCompanyId as string),
    enabled: Boolean(activeCompanyId),
  })
  const usersQuery = useQuery({
    queryKey: ['master-data', 'users', activeCompanyId],
    queryFn: () => masterDataService.listUsers(activeCompanyId as string),
    enabled: Boolean(activeCompanyId),
  })
  const costCentersQuery = useQuery({
    queryKey: ['master-data', 'cost-centers', activeCompanyId],
    queryFn: () => masterDataService.listCostCenters(activeCompanyId as string),
    enabled: Boolean(activeCompanyId),
  })
  const suppliersQuery = useQuery({
    queryKey: ['procurement', 'suppliers', activeCompanyId],
    queryFn: () => procurementService.listSuppliers(activeCompanyId as string),
    enabled: Boolean(activeCompanyId),
  })
  const projects = Array.isArray(projectsQuery.data) ? projectsQuery.data : []
  const customers = Array.isArray(customersQuery.data) ? customersQuery.data : []
  const users = Array.isArray(usersQuery.data) ? usersQuery.data : []
  const costCenters = Array.isArray(costCentersQuery.data) ? costCentersQuery.data : []
  const suppliers = Array.isArray(suppliersQuery.data) ? suppliersQuery.data : []

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['projects'] })
    queryClient.invalidateQueries({ queryKey: ['dashboard', 'summary'] })
    queryClient.invalidateQueries({ queryKey: ['procurement', 'contracts'] })
    queryClient.invalidateQueries({ queryKey: ['contract-payments'] })
  }

  const quickCreate = useMutation({
    mutationFn: () => projectService.create({
      companyId: activeCompanyId as string,
      name: quickProjectName.trim(),
      currencyCode: activeCompany?.functionalCurrencyCode as string | undefined,
    }),
    onSuccess: (project) => {
      invalidate()
      setQuickCreateOpen(false)
      setQuickProjectName('')
      setActiveProject(project.id)
      navigate(`/proyectos/${project.id}`)
    },
  })

  const columns: TableColumn<Project>[] = [
    { key: 'code', header: 'Código', render: (row) => row.code ?? '—' },
    {
      key: 'name', header: 'Proyecto', render: (row) => (
        <button className="nx-link-button" type="button" onClick={() => navigate(`/proyectos/${row.id}`)}>{row.name}</button>
      ),
    },
    { key: 'status', header: 'Estado', render: (row) => <Badge>{projectStatusLabel(row.status)}</Badge> },
    { key: 'manager', header: 'Responsable', render: (row) => row.manager ?? '—' },
    { key: 'dates', header: 'Plan', render: (row) => row.plannedStart && row.plannedEnd ? `${row.plannedStart} → ${row.plannedEnd}` : '—' },
    {
      key: 'selected', header: 'Contexto', render: (row) => context.activeProjectId === row.id ? (
        <Badge tone="info">Seleccionado</Badge>
      ) : <Button variant="secondary" onClick={() => setActiveProject(row.id)}>Seleccionar</Button>,
    },
    { key: 'actions', header: 'Acciones', render: (row) => <Button variant="secondary" onClick={() => navigate(`/proyectos/${row.id}`)}>Abrir</Button> },
  ]

  if (companiesLoading) return <LoadingState label="Cargando compañía…" />
  if (companiesError) return <ErrorState description="No se pudo cargar la compañía." onRetry={() => refetch()} />
  if (!activeCompanyId || !activeCompany) {
    if (companies.length === 0) {
      return (
        <div>
          <header className="nx-page__header">
            <h1 className="nx-dashboard__title">Proyectos</h1>
            <p className="nx-field__hint">Para crear proyectos, fases WBS, contratos y pagos primero se debe registrar una compañía.</p>
          </header>
          <Card title="Configuración inicial · crear compañía">
            <CompanyBootstrapForm />
          </Card>
        </div>
      )
    }
    return <EmptyState icon="project" title="Selecciona una compañía" description="Selecciona la empresa activa en la barra superior para gestionar proyectos." />
  }

  return (
    <div>
      <header className="nx-page__header">
        <div>
          <h1 className="nx-dashboard__title">Proyectos</h1>
          <p className="nx-field__hint">Empresa activa: {activeCompany.name}. El alta guiada puede dejar WBS, presupuesto, contrato, plan y documentos listos antes de activar.</p>
        </div>
        <div className="nx-page__actions">
          <Button variant="secondary" onClick={() => { setQuickCreateOpen((open) => !open); setWizardOpen(false) }}>
            {quickCreateOpen ? 'Cerrar alta rápida' : 'Crear proyecto básico'}
          </Button>
          <Button onClick={() => { setWizardOpen((open) => !open); setQuickCreateOpen(false) }}>
            {wizardOpen ? 'Cerrar asistente' : 'Proyecto con configuración completa'}
          </Button>
        </div>
      </header>

      {quickCreateOpen ? (
        <Card title="Nuevo proyecto · alta básica">
          <form onSubmit={(event) => { event.preventDefault(); if (activeCompanyId && quickProjectName.trim() && !quickCreate.isPending) quickCreate.mutate() }}>
            <p className="nx-field__hint">
              Crea el proyecto como borrador con su nombre. Después puedes configurar fases WBS, presupuesto, contratos y pagos sin adjuntar archivos para comenzar.
            </p>
            <Input
              label="Nombre del proyecto"
              value={quickProjectName}
              required
              maxLength={255}
              onChange={(event) => setQuickProjectName(event.target.value)}
            />
            {quickCreate.isError ? <p role="alert" className="nx-field__error">{(quickCreate.error as Error).message}</p> : null}
            <Button type="submit" disabled={!quickProjectName.trim() || quickCreate.isPending} loading={quickCreate.isPending}>
              Guardar proyecto básico
            </Button>
          </form>
        </Card>
      ) : null}

      {wizardOpen ? (
        <Card title="Nuevo proyecto — configuración operacional">
          <ProjectWizard
            companyId={activeCompanyId}
            functionalCurrencyCode={activeCompany.functionalCurrencyCode as string}
            customers={customers}
            users={users}
            costCenters={costCenters}
            suppliers={suppliers}
            onCreated={(project) => {
              invalidate()
              setWizardOpen(false)
              setActiveProject(project.id)
      navigate(`/proyectos/${project.id}`)
            }}
          />
        </Card>
      ) : null}

      <FilterBar onClear={() => { setFilterStatus(''); setFilterText(''); setShowArchived(false) }}>
        <Input label="Buscar proyecto" value={filterText} onChange={(event) => setFilterText(event.target.value)} placeholder="Nombre o código…" />
        <Select label="Estado" value={filterStatus} onChange={(event) => setFilterStatus(event.target.value)}>
          <option value="">Todos</option>
          {FILTERABLE_STATUSES.map((s) => <option key={s} value={s}>{PROJECT_STATUS_LABELS[s]}</option>)}
          <option value="ARCHIVED">Archivados</option>
        </Select>
        <div className="nx-field">
          <span className="nx-field__label">Archivados</span>
          <Button variant={showArchived ? 'secondary' : 'ghost'} onClick={() => setShowArchived((v) => !v)}>{showArchived ? 'Ocultar archivados' : 'Mostrar archivados'}</Button>
        </div>
      </FilterBar>

      {projectsQuery.isLoading ? <LoadingState label="Cargando proyectos…" /> : projectsQuery.isError ? (
        <ErrorState description="No se pudieron cargar los proyectos." onRetry={() => projectsQuery.refetch()} />
      ) : projects.length > 0 ? (
        <Table
          columns={columns}
          rows={projects.filter((row) => !filterText || row.name.toLowerCase().includes(filterText.toLowerCase()) || (row.code ?? '').toLowerCase().includes(filterText.toLowerCase()))}
          getRowKey={(row) => row.id}
        />
      ) : <EmptyState icon="project" title="Sin proyectos" description="No hay proyectos que coincidan con el filtro." />}
    </div>
  )
}
