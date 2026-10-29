import { NavList } from './NavList'

export function Sidebar() {
  return (
    <aside className="nx-sidebar">
      <div className="nx-sidebar__brand" aria-label="S4P Enterprise Platform">
        <img className="nx-sidebar__brand-logo" src="/s4p-logo.svg" alt="S4P Enterprise Platform" />
      </div>
      <NavList />
    </aside>
  )
}
