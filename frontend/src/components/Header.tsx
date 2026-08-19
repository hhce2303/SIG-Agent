import { ChevronDown, CircleUserRound } from 'lucide-react'
import Logo from './Logo'
import { useEngineStore } from '../stores/engineStore'

type HeaderProps = {
  center?: React.ReactNode
  role?: string
}

export default function Header({ center, role = 'Online' }: HeaderProps) {
  const userName = useEngineStore((state) => state.userName)
  const connection = useEngineStore((state) => state.connection)
  return (
    <header className="topbar">
      <Logo />
      <div className="topbar-center">{center}</div>
      <div className="user-chip">
        <div className="user-avatar"><CircleUserRound size={30} /></div>
        <div className="user-meta">
          <strong>{userName}</strong>
          <span><i className={`status-dot ${connection === 'connected' ? 'success' : 'warning'}`} />{role === 'Online' ? connection : role}</span>
        </div>
        <ChevronDown size={16} className="muted" />
      </div>
    </header>
  )
}
