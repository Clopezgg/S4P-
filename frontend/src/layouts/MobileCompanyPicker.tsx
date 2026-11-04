import { useActiveCompany } from '../hooks/useActiveCompany'

/** Same company selection as desktop, available from both mobile nav drawers. */
export function MobileCompanyPicker({ onSelected }: { onSelected: () => void }) {
  const { activeCompanyId, companies, setActiveCompanyId, isLoading } = useActiveCompany()

  return (
    <div className="nx-sap-mobile-company">
      <label htmlFor="s4p-mobile-company">Empresa activa</label>
      <select
        id="s4p-mobile-company"
        value={activeCompanyId ?? ''}
        onChange={(event) => {
          setActiveCompanyId(event.target.value || null)
          onSelected()
        }}
        disabled={isLoading || companies.length === 0}
      >
        {!activeCompanyId ? <option value="">Seleccionar empresa</option> : null}
        {companies.map((company) => (
          <option key={company.id} value={company.id}>{company.name}</option>
        ))}
      </select>
    </div>
  )
}
