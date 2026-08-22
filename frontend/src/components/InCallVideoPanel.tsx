import { Film, X } from 'lucide-react'
import { useState } from 'react'

// Escenarios de video — pedido explícito del usuario: poder ver el video DURANTE la
// simulación de la llamada, no solo antes. El plan original lo dejaba fuera a propósito (ver
// PreCallVideoGate.tsx: "video visible durante la llamada convertiría el ejercicio en leer en
// voz alta") — se mantiene esa preocupación, pero como algo que el entrenando elige activamente
// (cerrado por default, un botón para abrirlo), no como el video puesto en pantalla sin pedirlo.
// Nunca autoplay: abrir el panel no reanuda el video solo, así como cerrarlo no lo pausa por
// arte de magia — el `<video>` nativo ya trae sus propios controles para eso.
export default function InCallVideoPanel({ streamUrl }: { streamUrl: string }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="in-call-video-panel">
      {open && (
        <div className="in-call-video-frame panel">
          <button className="in-call-video-close" onClick={() => setOpen(false)} aria-label="Close video">
            <X size={16} />
          </button>
          {/* eslint-disable-next-line jsx-a11y/media-has-caption -- mismo video ya subtitulado en el gate pre-llamada; sin captions nuevas acá */}
          <video className="in-call-video-el" src={streamUrl} controls />
        </div>
      )}
      <button className="in-call-video-toggle secondary-button" onClick={() => setOpen((v) => !v)}>
        <Film size={16} />{open ? 'Hide video' : 'Watch video again'}
      </button>
    </div>
  )
}
