import { useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Input, Select } from '../../design-system'
import { useActiveCompany } from '../../hooks/useActiveCompany'
import { masterDataService } from '../../services/masterDataService'

/**
 * First-run onboarding for databases seeded with RBAC + Administrator but no
 * company. No implicit financial data, projects or transactions are created.
 */
export function CompanyBootstrapForm() {
  const queryClient = useQueryClient()
  const { setActiveCompanyId } = useActiveCompany()
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [currencyCode, setCurrencyCode] = useState('HNL')
  const [country, setCountry] = useState('HN')

  const create = useMutation({
    mutationFn: () => masterDataService.createCompany({
      name: name.trim(),
      code: code.trim() || undefined,
      functionalCurrencyCode: currencyCode,
      country,
    }),
    onSuccess: async (company) => {
      await queryClient.invalidateQueries({ queryKey: ['master-data', 'companies'] })
      setActiveCompanyId(company.id)
    },
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim() || create.isPending) return
    create.mutate()
  }

  return (
    <form onSubmit={submit} aria-label="Crear primera compañía">
      <p className="nx-field__hint">
        Esta instalación todavía no tiene una compañía. Registra la empresa
        para habilitar Proyectos, WBS, contratos, pagos y tesorería.
        No se creará ningún movimiento financiero automáticamente.
      </p>
      <Input
        label="Nombre de la compañía"
        value={name}
        maxLength={255}
        required
        onChange={(event) => setName(event.target.value)}
        placeholder="Nombre comercial o razón social"
      />
      <Input
        label="Código de compañía (opcional)"
        value={code}
        maxLength={32}
        onChange={(event) => setCode(event.target.value)}
        placeholder="Código interno"
      />
      <Select
        label="Moneda funcional"
        value={currencyCode}
        onChange={(event) => setCurrencyCode(event.target.value)}
      >
        <option value="HNL">HNL — Lempira</option>
        <option value="USD">USD — Dólar estadounidense</option>
        <option value="EUR">EUR — Euro</option>
      </Select>
      <Select label="País" value={country} onChange={(event) => setCountry(event.target.value)}>
        <option value="HN">Honduras</option>
        <option value="US">Estados Unidos</option>
        <option value="ES">España</option>
      </Select>
      <p className="nx-field__hint">
        El código y la moneda funcional pueden volverse inmutables después de
        registrarse. Comprueba esos datos antes de continuar.
      </p>
      {create.isError ? (
        <p role="alert" className="nx-field__error">
          {(create.error as Error).message}. Confirma que el usuario tenga permiso
          para crear compañías.
        </p>
      ) : null}
      <Button type="submit" disabled={!name.trim()} loading={create.isPending}>
        Crear compañía y habilitar operaciones
      </Button>
    </form>
  )
}
