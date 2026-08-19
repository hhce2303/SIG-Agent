# Glosario — voice-agent

Un término, una definición. Si el código, la conversación o la documentación usan una palabra
distinta para lo mismo, es un defecto a resolver, no un sinónimo a tolerar.

| Término | Definición |
|---|---|
| **Supervisor / trainee** | Empleado del concesionario que practica reportar un incidente a la policía. Usuario final del producto. |
| **Dispatcher** | El rol de despachador policial que interpreta el LLM (Claude) durante la llamada de práctica. No es un asistente de IA genérico — nunca sale de personaje. |
| **Escenario** | Configuración de una llamada de práctica: qué incidente ocurrió, qué datos tiene el llamante, qué debe extraer el dispatcher. Campos estructurados (título, categoría, dificultad, `critical_data_points`) + una narrativa libre (`briefing`) — ver `core/ports.py::Scenario`, editable por el usuario (Fase 2, TODO-11 resuelto). El `SCENARIO` string de `vehicle_theft.py` sigue existiendo tal cual solo para el prototipo CLI (NFR-03). |
| **Sesión** | Una llamada de práctica completa, de inicio a fin, junto con su transcript, métricas y metadatos — la unidad que vive en el historial. |
| **Turno** | Una unidad de intercambio de habla: el supervisor habla, el dispatcher responde. La transición entre turnos es lo que VAD detecta automáticamente. |
| **VAD (Voice Activity Detection)** | Detección automática de inicio/fin de habla, reemplaza el botón de push-to-talk del prototipo. Ver [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md). |
| **Barge-in** | Capacidad de interrumpir al otro lado mientras habla (superposición de voces). Explícitamente fuera de alcance en Fase 1-2 — ver ADR-0005. |
| **Corte falso (false cutoff)** | Cuando VAD termina el turno del supervisor antes de que realmente haya terminado de hablar (ej. una pausa mientras piensa la placa). Requiere un estado de recuperación definido en el cliente. |
| **Ponderado / score** | Evaluación numérica de qué tan efectiva fue una sesión. Fórmula (TODO-10 resuelto, Fase 2): completitud 40% / tiempo-a-dato-crítico 30% / claridad 20% / tiempo total 10% — ver `core/scoring.py::ScoreWeights`, configurable por variables de entorno. |
| **Spike** | Prueba técnica acotada en el tiempo para validar o refutar una hipótesis de arquitectura antes de comprometer alcance de una fase completa (ver Gate 0 en el roadmap). |
| **Concesionario** | Sitio físico (dealership) donde trabajan los supervisores. El proyecto asume una sola ubicación (ver GOALS.md, Alcance confirmado). |
| **Servidor LAN** | La máquina con GPU RTX que corre STT/TTS (y expone el WebSocket) dentro de la red interna del concesionario. Ver [ADR-0004](./adr/0004-topologia-de-despliegue.md). |
| **Cliente** | La aplicación Electron/React/Tailwind que usa el supervisor para sostener la llamada. Ver [ADR-0002](./adr/0002-frontend-electron-react-tailwind.md). |
| **ADR** | Architecture Decision Record — una decisión estructural, su contexto y su razón, registrada en `docs/architecture/adr/`. Nunca se borra; se marca `superseded`. |
| **NFR** | Non-Functional Requirement — un requisito de calidad medible (latencia, disponibilidad, privacidad), registrado con ID estable en `nfr.md`. |
| **Incidente real** | Un incidente real (no de práctica) ya resuelto, registrado a mano en el sistema (roadmap Fase 3) — fecha, supervisor, resultado, y notas de post-mortem. Ver `core/ports.py::IncidentOutcome`. No se confunde con "sesión" (una llamada de práctica) ni con "escenario" (la configuración de una práctica). |
| **Entrenado (para un incidente)** | Se deriva, nunca se captura a mano: un supervisor cuenta como "entrenado" respecto a un incidente real si tiene al menos una sesión de práctica puntuada (`outcome == "ended"`) que terminó antes de la fecha de ese incidente. Ver `core/impact_metrics.py`. |
| **Lazo de retroalimentación** | Promover el post-mortem de un incidente real a un borrador de `Scenario` en la librería (roadmap Fase 3, "cierre del círculo entre por qué se construyó esto y qué se practica"). Ver `POST /incidents/{id}/promote-to-scenario`. |
