"""Métrica de resultado real — roadmap Fase 3 ("cierre del lazo de impacto real").

Dominio puro (ADR-0006): no importa FastAPI ni ningún adaptador de persistencia concreto, igual
que `core/scoring.py`. Opera sobre datos ya cargados (`IncidentOutcome` + `SessionRecord`), sin
llamar a un reloj ni a una base de datos.

Objetivo del roadmap: "correlacionar desempeño de supervisores entrenados vs. no entrenados en
incidentes reales — sin esto, la herramienta puede tener 100% de uso y 0% de impacto medible."

Decisión de diseño: "entrenado" nunca se captura a mano en el incidente (ver `IncidentOutcome`,
`core/ports.py`) — se DERIVA de si ese supervisor tiene al menos una sesión de práctica real
(`SessionRecord.outcome == "ended"`, es decir puntuada, no una interrumpida por caída de red)
que haya terminado antes de `occurred_at`. Esto evita que la métrica dependa de que alguien
recuerde o reporte correctamente si el supervisor "ya había entrenado" — el propio sistema ya
tiene esa respuesta en `PersistencePort`.

Exposición deliberadamente agregada: este módulo nunca devuelve qué supervisor específico tuvo
qué resultado — la política de visibilidad self-only (TODO-04, roadmap Fase 2) sigue vigente
para el historial de sesiones; el reporte de impacto solo expone conteos y promedios por grupo
(entrenado/no entrenado), nunca un cruce nombre-de-supervisor + resultado individual.
"""

from dataclasses import dataclass, field

from core.ports import IncidentOutcome, SessionRecord

# Por debajo de esto, el reporte se marca explícitamente como no concluyente — un promedio de 2
# incidentes por grupo no es evidencia, es ruido. No hay un ADR para este número: es un umbral
# de calibración estadística mínima, igual de espíritu a las bandas de `core/scoring.py`.
MIN_SAMPLE_SIZE_FOR_CONFIDENCE = 5


@dataclass(frozen=True)
class GroupStats:
    sample_size: int = 0
    avg_outcome_rating: float | None = None
    critical_data_capture_rate: float | None = None
    protocol_followed_rate: float | None = None


@dataclass(frozen=True)
class ImpactReport:
    trained: GroupStats
    untrained: GroupStats
    total_incidents: int
    is_conclusive: bool
    caveat: str


def _was_trained_before(
    incident: IncidentOutcome, sessions_by_supervisor: dict[str, list[SessionRecord]]
) -> bool:
    sessions = sessions_by_supervisor.get(incident.supervisor_id, [])
    return any(
        session.outcome == "ended"
        and session.ended_at is not None
        and session.ended_at < incident.occurred_at
        for session in sessions
    )


def _group_stats(incidents: list[IncidentOutcome]) -> GroupStats:
    if not incidents:
        return GroupStats(sample_size=0)

    n = len(incidents)
    return GroupStats(
        sample_size=n,
        avg_outcome_rating=sum(i.outcome_rating for i in incidents) / n,
        critical_data_capture_rate=sum(1 for i in incidents if i.critical_data_captured) / n,
        protocol_followed_rate=sum(1 for i in incidents if i.protocol_followed) / n,
    )


def compute_impact_report(
    incidents: list[IncidentOutcome],
    sessions_by_supervisor: dict[str, list[SessionRecord]],
) -> ImpactReport:
    """`sessions_by_supervisor` ya viene resuelto (un `list_sessions` por cada `supervisor_id`
    distinto entre los incidentes) — este módulo no decide cómo se consiguió, solo correlaciona.
    """

    trained_incidents = [i for i in incidents if _was_trained_before(i, sessions_by_supervisor)]
    trained_ids = {i.id for i in trained_incidents}
    untrained_incidents = [i for i in incidents if i.id not in trained_ids]

    trained = _group_stats(trained_incidents)
    untrained = _group_stats(untrained_incidents)

    is_conclusive = (
        trained.sample_size >= MIN_SAMPLE_SIZE_FOR_CONFIDENCE
        and untrained.sample_size >= MIN_SAMPLE_SIZE_FOR_CONFIDENCE
    )

    if not incidents:
        caveat = "No real incidents have been logged yet — nothing to correlate."
    elif is_conclusive:
        caveat = ""
    else:
        caveat = (
            f"Not enough data yet for a reliable comparison — each group needs at least "
            f"{MIN_SAMPLE_SIZE_FOR_CONFIDENCE} logged incidents "
            f"(trained: {trained.sample_size}, untrained: {untrained.sample_size})."
        )

    return ImpactReport(
        trained=trained,
        untrained=untrained,
        total_incidents=len(incidents),
        is_conclusive=is_conclusive,
        caveat=caveat,
    )
