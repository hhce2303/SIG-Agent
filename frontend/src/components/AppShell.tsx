import Header from './Header'
import Sidebar from './Sidebar'
import { useEngineStore } from '../stores/engineStore'

export default function AppShell({ children, active, role }: { children: React.ReactNode; active?: string; role?: string }) {
  const connection = useEngineStore((state) => state.connection)
  return (
    <div className="app-frame">
      <Header role={role} />
      <Sidebar activeOverride={active} />
      <main className="shell-content">{children}</main>
      <footer className="statusbar">
        <span><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} />Voice Engine: <strong>{connection}</strong></span>
        <span className="secure">◇ Local-only connection</span>
      </footer>
    </div>
  )
}
