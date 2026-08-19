import { BarChart3, BookOpen, ClipboardList, Headphones, Home, Settings, TrendingUp } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const items = [
  { to: '/', label: 'Home', icon: Home },
  { to: '/training', label: 'Training', icon: Headphones },
  { to: '/performance', label: 'Performance', icon: BarChart3 },
  { to: '/scenarios', label: 'Scenarios', icon: ClipboardList },
  // Fase 3 (roadmap): "cierre del lazo de impacto real" — correlación contra incidentes reales.
  { to: '/impact', label: 'Impact', icon: TrendingUp },
  { to: '/resources', label: 'Resources', icon: BookOpen },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar({ activeOverride }: { activeOverride?: string }) {
  return (
    <aside className="sidebar">
      <nav className="sidebar-nav">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={label}
            to={to}
            className={({ isActive }) => `nav-item ${(activeOverride === label || (!activeOverride && isActive && label === 'Home')) ? 'active' : ''}`}
          >
            <Icon size={23} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-footer">
        <ShieldMini />
        <div><strong>v0.2.0</strong><span>Voice engine enabled</span></div>
      </div>
    </aside>
  )
}

function ShieldMini() {
  return <div className="mini-shield">S</div>
}
