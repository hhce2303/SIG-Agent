import { useRef } from 'react'

// Ubicación del incidente — docs/designs/ubicacion-del-incidente.md, Fase 2 (hallazgos F17/F18)
// y Fase 3 Sección 1.
//
// Un solo componente, 3 modos (evita triplicar este SVG — Fase 2 Pass 5):
// - "author": ScenarioEditorPage.tsx — interactivo, coloca el flag por clic o por teclado.
// - "brief":  PreCallLocationBriefing.tsx / InCallLocationPanel.tsx — solo lectura, contenido
//             completo (calle/cruce/referencia visibles al trainee — NO son la respuesta oculta,
//             ver 0A punto 1 del design doc).
// - "review": SessionBreakdown.tsx — solo lectura, con overlay verde/gris de qué se mencionó.
//
// Hallazgo F17 (el más importante de la revisión de diseño): un flag sin nada respecto a qué
// posicionarlo no representa nada. Este componente dibuja `street` como una línea horizontal y
// `cross_street` como una línea vertical que se cruzan en el centro del lienzo — el flag se
// posiciona con un offset (`markerX`/`markerY`, 0..1) respecto a esa intersección, así que su
// posición SÍ significa algo ("esquina noreste de 5th Ave y Main St"). `landmark`, si existe, es
// un cuadrado pequeño con su propia etiqueta.
//
// Tokens de Pass 5 (Fase 2) — nunca un color hardcodeado nuevo fuera de esta lista.
const COLORS = {
  canvasBg: 'var(--bg-deep)',
  canvasBorder: 'var(--border)',
  track: 'var(--track)',
  label: 'var(--muted)',
  marker: 'var(--danger)',
  compass: 'var(--muted-2)',
  ok: 'var(--success)',
  bad: 'var(--muted-2)',
}

export type LocationMiniMapMode = 'author' | 'brief' | 'review'

export type LocationMiniMapValue = {
  street: string
  crossStreet: string
  landmark: string
  markerX: number | null
  markerY: number | null
}

export default function LocationMiniMap({
  mode,
  value,
  size = mode === 'brief' ? 320 : mode === 'review' ? 220 : 240,
  collectedLabels,
  onMarkerChange,
}: {
  mode: LocationMiniMapMode
  value: LocationMiniMapValue
  size?: number
  // "review" only — evaluation.collected ya trae labels como "Street: 5th Avenue" (ver
  // core/scoring.py::_location_critical_points) — se resalta en verde lo que está presente ahí.
  collectedLabels?: string[]
  // "author" only — clic o teclado mueve el marcador. Ausente = solo lectura (brief/review).
  onMarkerChange?: (x: number, y: number) => void
}) {
  const svgRef = useRef<SVGSVGElement>(null)
  const interactive = mode === 'author' && !!onMarkerChange

  const hasStreet = value.street.trim().length > 0
  const hasCrossStreet = value.crossStreet.trim().length > 0
  const hasLandmark = value.landmark.trim().length > 0
  const hasMarker = value.markerX !== null && value.markerY !== null

  const center = size / 2
  // Offset del flag respecto a la intersección — markerX/markerY son 0..1 sobre TODO el lienzo,
  // no relativos al centro, para que el round-trip con el backend sea directo (mismos valores que
  // se persisten). 0.5/0.5 = exactamente la intersección.
  const markerPixelX = hasMarker ? (value.markerX as number) * size : center
  const markerPixelY = hasMarker ? (value.markerY as number) * size : center

  const streetCollected = collectedLabels?.includes(`Street: ${value.street}`) ?? false
  const crossStreetCollected = collectedLabels?.includes(`Cross street: ${value.crossStreet}`) ?? false
  const landmarkCollected = collectedLabels?.includes(`Landmark: ${value.landmark}`) ?? false

  const streetColor = mode === 'review' ? (streetCollected ? COLORS.ok : COLORS.bad) : COLORS.track
  const crossStreetColor = mode === 'review' ? (crossStreetCollected ? COLORS.ok : COLORS.bad) : COLORS.track
  const landmarkColor = mode === 'review' ? (landmarkCollected ? COLORS.ok : COLORS.bad) : COLORS.track

  const positionWords = describePosition(value)

  function placeMarkerFromEvent(clientX: number, clientY: number) {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || !onMarkerChange) return
    const x = clamp01((clientX - rect.left) / rect.width)
    const y = clamp01((clientY - rect.top) / rect.height)
    onMarkerChange(x, y)
  }

  function handleKeyDown(event: React.KeyboardEvent<SVGSVGElement>) {
    if (!onMarkerChange) return
    const step = event.shiftKey ? 0.1 : 0.02
    const currentX = value.markerX ?? 0.5
    const currentY = value.markerY ?? 0.5
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    }
    const move = moves[event.key]
    if (!move) return
    event.preventDefault()
    onMarkerChange(clamp01(currentX + move[0]), clamp01(currentY + move[1]))
  }

  return (
    <div className="location-minimap-wrap">
      <svg
        ref={svgRef}
        className="location-minimap"
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        role={interactive ? 'application' : 'img'}
        aria-label={
          interactive
            ? `Incident location map. Marker is ${positionWords}. Use arrow keys to move it, or click on the map.`
            : `Incident location map: ${positionWords}.`
        }
        tabIndex={interactive ? 0 : undefined}
        onClick={interactive ? (event) => placeMarkerFromEvent(event.clientX, event.clientY) : undefined}
        onKeyDown={interactive ? handleKeyDown : undefined}
        style={{ cursor: interactive ? 'crosshair' : 'default' }}
      >
        <rect
          x={0.5} y={0.5} width={size - 1} height={size - 1} rx={12}
          fill={COLORS.canvasBg} stroke={COLORS.canvasBorder}
        />

        {/* Rosa de los vientos — 4 marcas de línea fina, funcional (orienta la geometría real de
            abajo) en vez de decorativa (F17/Pass 4). Fija arriba a la derecha. */}
        <CompassRose x={size - 34} y={34} />

        {/* Calle (horizontal) / cruce (vertical) — F17: le dan al flag algo respecto a qué
            posicionarse. Solo se dibujan si el autor configuró ese campo. */}
        {hasStreet && (
          <>
            <line x1={12} y1={center} x2={size - 12} y2={center} stroke={streetColor} strokeWidth={2} />
            <text x={16} y={center - 6} fill={COLORS.label} fontSize={11}>
              {truncateLabel(value.street)}
            </text>
          </>
        )}
        {hasCrossStreet && (
          <>
            <line x1={center} y1={12} x2={center} y2={size - 12} stroke={crossStreetColor} strokeWidth={2} />
            <text x={center + 6} y={22} fill={COLORS.label} fontSize={11}>
              {truncateLabel(value.crossStreet)}
            </text>
          </>
        )}
        {hasLandmark && (
          <>
            <rect x={size * 0.72 - 5} y={size * 0.72 - 5} width={10} height={10} fill="none" stroke={landmarkColor} strokeWidth={2} />
            <text x={size * 0.72 + 9} y={size * 0.72 + 4} fill={COLORS.label} fontSize={11}>
              {truncateLabel(value.landmark)}
            </text>
          </>
        )}

        {/* El flag — un triángulo de línea fina, nunca un pin relleno tipo Google Maps ni un
            emoji (Pass 4: ambos son slop reconocible, y un pin de mapa contradice "no se
            necesita un motor de geolocalización como el de Google"). */}
        {hasMarker || interactive ? (
          <g transform={`translate(${markerPixelX}, ${markerPixelY})`}>
            <path d="M0,-16 L0,2 M0,-16 L9,-11 L0,-6 Z" fill="none" stroke={COLORS.marker} strokeWidth={1.7} />
          </g>
        ) : null}
      </svg>
      {interactive && <p aria-live="polite" className="location-minimap-live-region">{positionWords}</p>}
    </div>
  )
}

function CompassRose({ x, y }: { x: number; y: number }) {
  const r = 14
  return (
    <g stroke="var(--muted-2)" strokeWidth={1} fill="none">
      <line x1={x} y1={y - r} x2={x} y2={y + r} />
      <line x1={x - r} y1={y} x2={x + r} y2={y} />
      <text x={x} y={y - r - 4} fill="var(--muted)" fontSize={10} textAnchor="middle" stroke="none">N</text>
    </g>
  )
}

function describePosition(value: LocationMiniMapValue): string {
  if (value.markerX === null || value.markerY === null) return 'not placed yet'
  const vertical = value.markerY < 0.45 ? 'north' : value.markerY > 0.55 ? 'south' : ''
  const horizontal = value.markerX < 0.45 ? 'west' : value.markerX > 0.55 ? 'east' : ''
  const direction = [vertical, horizontal].filter(Boolean).join('-') || 'at the intersection'
  const street = value.street.trim() || 'the configured street'
  const crossStreet = value.crossStreet.trim()
  return crossStreet ? `${direction} of ${street} and ${crossStreet}` : `${direction} of ${street}`
}

function truncateLabel(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}
