import { lazy, Suspense } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { dashboardService } from '../../services/dashboardService'
import { formatMoney } from '../../utils/currency'
import { ApiError } from '../../services/httpClient'
import { useAuth } from '../auth/auth-context'
import { useActiveContext } from '../context/useActiveContext'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { resolveHomeConfig } from './roleHomes'
import { MiTrabajoHoy } from './MiTrabajoHoy'
import { HomeForecastCard } from './HomeForecastCard'
import { HomeBankAccountsCard } from './HomeBankAccountsCard'
import { Card, EmptyState, ErrorState, Icon, LoadingState, StatCard } from '../../design-system'
import { ProjectWorkHome } from './ProjectWorkHome'
import './HomePage.css'

const FinancialCharts = lazy(() => import('./FinancialCharts'))

export function HomePage() {
  const { user } = useAuth()
  const { activeCompany, activeCompanyId } = useActiveCompany()
  const { context } = useActiveContext()
  const config = resolveHomeConfig(user?.roles ?? [])

  const companySummaryQuery = useQuery({
    queryKey: ['dashboard', 'summary', activeCompanyId],
    // React Query aborts this request on unmount/navigation. Do not leave
    // dashboard fetches active after logout (WebKit treats the abort as a page error).
    queryFn: ({ signal }) => dashboardService.getSummary(activeCompanyId, signal),
    enabled: config.showTreasurySummary && Boolean(activeCompanyId) && !context.activeProjectId,
  })
  const error = companySummaryQuery.error
  const sessionExpired = error instanceof ApiError && error.status === 401

  if (context.activeProjectId) return <ProjectWorkHome key={context.activeProjectId} projectId={context.activeProjectId} />

  return (
    <div className="nx-home">
      <header className="nx-home__header">
        <div>
          <p className="nx-home__eyebrow">Vista empresa</p>
          <h1 className="nx-dashboard__title">{config.title}</h1>
          <p className="nx-home__subtitle">{activeCompany?.name ?? config.subtitle} · Tesorería y operación consolidada de la empresa.</p>
        </div>
      </header>

      {!activeCompanyId ? (
        <EmptyState title="Sin empresa activa" description="Selecciona o configura una compañía para cargar el dashboard." />
      ) : config.showTreasurySummary ? (
        companySummaryQuery.isLoading ? (
          <LoadingState label="Cargando indicadores…" />
        ) : companySummaryQuery.isError || !companySummaryQuery.data ? (
          <ErrorState
            title={sessionExpired ? 'Tu sesión necesita renovarse' : 'No se pudo cargar el dashboard'}
            description={sessionExpired ? 'Cierra sesión y vuelve a ingresar para continuar.' : 'No fue posible cargar los indicadores de la empresa.'}
            onRetry={() => companySummaryQuery.refetch()}
          />
        ) : (
          <>
            <section className="nx-home__grid nx-home__grid--kpi" aria-label="Indicadores financieros">
              <StatCard
                icon={<span className="nx-kpi-tile nx-kpi-tile--treasury"><Icon name="bank" /></span>}
                label="Tesorería · disponible"
                value={formatMoney(companySummaryQuery.data.treasuryBalance, companySummaryQuery.data.currency)}
              />
              <StatCard
                icon={<span className="nx-kpi-tile nx-kpi-tile--income"><Icon name="chart" /></span>}
                label={companySummaryQuery.data.fiscalPeriodLabel ? `Ingresos · ${companySummaryQuery.data.fiscalPeriodLabel}` : 'Ingresos del mes calendario'}
                value={formatMoney(companySummaryQuery.data.periodIncome, companySummaryQuery.data.currency)}
              />
              <StatCard
                icon={<span className="nx-kpi-tile nx-kpi-tile--expense"><Icon name="receipt" /></span>}
                label={companySummaryQuery.data.fiscalPeriodLabel ? `Gastos · ${companySummaryQuery.data.fiscalPeriodLabel}` : 'Gastos del mes calendario'}
                value={formatMoney(companySummaryQuery.data.periodExpense, companySummaryQuery.data.currency)}
              />
              <StatCard
                icon={<span className="nx-kpi-tile nx-kpi-tile--projects"><Icon name="project" /></span>}
                label="Proyectos en ejecución"
                value={companySummaryQuery.data.activeProjects}
              />
            </section>

            {!companySummaryQuery.data.fiscalPeriodLabel ? (
              <Card title="Período fiscal no configurado">
                <p>Mientras no exista un período fiscal actual, Ingresos y Gastos se muestran como mes calendario y se etiquetan explícitamente así.</p>
                <Link to="/control/configuracion">Configurar períodos fiscales</Link>
              </Card>
            ) : null}

            <MiTrabajoHoy summary={companySummaryQuery.data} />

            <HomeForecastCard companyId={activeCompanyId} />

            <HomeBankAccountsCard companyId={activeCompanyId} />

            <Suspense fallback={<LoadingState label="Preparando gráficos…" />}>
              <FinancialCharts
                cashFlow={companySummaryQuery.data.cashFlow ?? []}
                expensesByScope={companySummaryQuery.data.expensesByScope ?? []}
                currency={companySummaryQuery.data.currency}
              />
            </Suspense>
          </>
        )
      ) : null}

      <section className="nx-home__sections" aria-label="Accesos principales">
        {config.sections.map((section) => (
          <Link key={section.title} className="nx-home__quick-link" to={section.path}>
            <Card title={section.title}>
              <p>{section.description}</p>
              <span className="nx-home__quick-action">Abrir módulo</span>
            </Card>
          </Link>
        ))}
      </section>
    </div>
  )
}
