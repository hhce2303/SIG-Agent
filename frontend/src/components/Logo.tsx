import { Headphones, Shield } from 'lucide-react'

export default function Logo() {
  return (
    <div className="brand">
      <div className="brand-mark" aria-hidden="true">
        <Shield size={42} strokeWidth={1.7} />
        <Headphones className="brand-headphones" size={20} strokeWidth={2} />
      </div>
      <div>
        <div className="brand-title">SIG Agent</div>
        <div className="brand-subtitle">POLICE CALL TRAINING SIMULATOR</div>
      </div>
    </div>
  )
}
