import { CompanySettingsPage } from './CompanySettingsPage'
import { AccessManagementSettings } from './AccessManagementSettings'
import './CompanySettingsWorkspace.css'

export function CompanySettingsWorkspace() {
  return (
    <div className="nx-page nx-company-settings-workspace">
      <CompanySettingsPage />
      <AccessManagementSettings />
    </div>
  )
}