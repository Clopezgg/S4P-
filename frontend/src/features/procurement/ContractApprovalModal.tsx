import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, Select } from '../../design-system'
import { useCompanyUsers } from '../../hooks/useCompanyUsers'
import { useMutationError } from '../../hooks/useMutationError'
import { procurementService } from '../../services/procurementService'
import type { SupplierContract } from '../../types/procurement'
import { useAuth } from '../auth/auth-context'

export function ContractApprovalModal({ contract, onClose }: {
  contract: SupplierContract
  onClose: () => void
}) {
  const { user } = useAuth()
  const { users, isLoading, isError } = useCompanyUsers(contract.companyId)
  const [assignedTo, setAssignedTo] = useState('')
  const queryClient = useQueryClient()
  const handleError = useMutationError()
  const mutation = useMutation({
    mutationFn: () => procurementService.submitContractForApproval(contract.id, assignedTo),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['procurement', 'contracts', contract.companyId] })
      await queryClient.invalidateQueries({ queryKey: ['approvals'] })
      onClose()
    },
    onError: (error) => handleError(error, 'Enviar contrato a aprobación'),
  })
  return (
    <Modal open title={`Enviar contrato ${contract.contractNumber} a aprobación`} onClose={onClose}>
      <form onSubmit={(event) => { event.preventDefault(); mutation.mutate() }}>
        <p>El aprobador debe ser distinto del solicitante y tener acceso a la empresa y al proyecto.</p>
        <Select name="contractApprover" label="Usuario aprobador" required value={assignedTo}
          onChange={(event) => setAssignedTo(event.target.value)} disabled={isLoading || isError}>
          <option value="">Selecciona un aprobador…</option>
          {users.filter((person) => person.id !== user?.id).map((person) => (
            <option key={person.id} value={person.id}>{person.fullName} ({person.email})</option>
          ))}
        </Select>
        {isError ? <p role="alert">No se pudo cargar el directorio de aprobadores.</p> : null}
        {mutation.isError ? <p role="alert">{(mutation.error as Error).message}</p> : null}
        <Button type="submit" disabled={!assignedTo || isLoading || isError} loading={mutation.isPending}>
          Enviar a aprobación
        </Button>
      </form>
    </Modal>
  )
}
