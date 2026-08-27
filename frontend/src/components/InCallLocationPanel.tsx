import { MapPin, X } from 'lucide-react'
import { useState } from 'react'
import LocationMiniMap from './LocationMiniMap'
import type { ScenarioLocationAccess } from '../types'

// Ubicación del incidente — docs/designs/ubicacion-del-incidente.md, hallazgo F12 (voz de
// diseño independiente): el borrador inicial rechazaba el acceso en vivo asumiendo "igual que
// video, se oculta durante la llamada" — falso, `InCallVideoPanel.tsx` ya existe, cerrado por
// default con un toggle opt-in, tras un pedido explícito del usuario que revirtió esa misma
// restricción para video. Este componente sigue el mismo patrón exacto: cerrado por default, el
// entrenando lo abre si lo necesita, nunca puesto en pantalla sin pedirlo — no invalida el
// ejercicio de comunicación porque requiere una acción deliberada, igual que ya pasa con video.
export default function InCallLocationPanel({ location }: { location: ScenarioLocationAccess }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="in-call-location-panel">
      {open && (
        <div className="in-call-location-frame panel">
          <button className="in-call-location-close" onClick={() => setOpen(false)} aria-label="Close location">
            <X size={16} />
          </button>
          <LocationMiniMap
            mode="brief"
            size={220}
            value={{
              street: location.street,
              crossStreet: location.cross_street,
              landmark: location.landmark,
              markerX: location.marker_x,
              markerY: location.marker_y,
            }}
          />
          <div className="in-call-location-text">
            {location.street && <p><strong>Street:</strong> {location.street}</p>}
            {location.cross_street && <p><strong>Cross street:</strong> {location.cross_street}</p>}
            {location.landmark && <p><strong>Landmark:</strong> {location.landmark}</p>}
          </div>
        </div>
      )}
      <button className="in-call-location-toggle secondary-button" onClick={() => setOpen((v) => !v)}>
        <MapPin size={16} />{open ? 'Hide location' : 'Check the address again'}
      </button>
    </div>
  )
}
