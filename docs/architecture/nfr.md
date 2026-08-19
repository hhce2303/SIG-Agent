# Non-Functional Requirements — voice-agent

IDs estables (`NFR-NN`). Referenciar por ID desde ADRs, TODOS.md y el design doc — nunca
copiar el texto completo en otro documento.

## Rendimiento

### NFR-01
**Latencia end-to-end.** Menor a 1.5s desde que el supervisor termina de hablar hasta que
empieza a sonar el audio de respuesta del dispatcher (STT → Claude API → TTS), con un ideal
aspiracional de <800ms. Criterio de validación de [ADR-0004](./adr/0004-topologia-de-despliegue.md).
Fuente: design doc de origen, sección Constraints.

## Confiabilidad

### NFR-02
**Recuperación en banda, no falla silenciosa.** Errores de la API de Claude (timeout,
rate-limit, error de red), cortes falsos de VAD, y degradación/caída de la conexión LAN deben
tener un estado de recuperación definido en el propio diálogo o en la UI — nunca un cuelgue sin
explicación. Ver [ADR-0005](./adr/0005-audio-en-vivo-vad-sin-barge-in.md) y la sección
"Eng/Architecture Requirements" del design doc de origen.

### NFR-03
**Continuidad ante caída del servidor LAN.** El prototipo CLI actual se mantiene funcional como
fallback manual mientras el servidor LAN (ver ADR-0004) madura y en caso de caída — un
supervisor siempre debe tener algo con qué entrenar.

## Seguridad

### NFR-04
**Autenticación por sesión.** El servidor WebSocket expuesto en la LAN requiere un mecanismo de
autenticación por supervisor y un token de sesión con scope por conexión (una conexión no debe
poder apuntar a la sesión de audio de otra). Mecanismo exacto: pendiente, ver TODOS.md.

### NFR-05
**Cifrado en tránsito.** Comunicación cliente-servidor sobre WSS/TLS como mínimo de Fase 1 — no
WebSocket sin cifrar, ni siquiera dentro de la LAN interna.

## Privacidad

### NFR-06
**Política de retención y visibilidad del historial.** Debe estar resuelta y comunicada antes
de almacenar audio/transcripts reales de práctica: cuánto tiempo se retienen, y quién puede
verlos (el propio supervisor, su jefe, RRHH). Sin esto, los supervisores no practican
honestamente — es un objetivo de calidad tanto como cualquier requisito técnico (ver GOALS.md).
Bloqueante de Fase 1 según el design doc de origen.

### NFR-07
**Cumplimiento regulatorio de grabación de voz.** No se confirmó ninguna restricción legal
conocida (ej. leyes estatales de consentimiento para grabar) al momento de este baseline —
queda como decisión pendiente en TODOS.md, no como supuesto de "no aplica".

## Observabilidad

### NFR-08
**Logging estructurado y confianza de transcripción.** Cada etapa del pipeline (audio recibido,
salida de STT + confianza por segmento, request/response de Claude + latencia, síntesis de TTS)
debe quedar en logs estructurados con id de correlación por sesión/turno, desde el día uno de
Fase 1 — no agregado después como parte del dominio de métricas.

## Calidad de datos

### NFR-09
**Confirmación de datos críticos.** Placas, VIN y otros datos alfanuméricos transcritos por STT
deben pasar por un paso de confirmación explícito en el diálogo del dispatcher cuando la
confianza de transcripción sea baja — un dato mal transcrito no debe quedar como "correcto" en
el score sin ninguna señal.

## Mantenibilidad

### NFR-10
**Cobertura de tests antes del rewrite.** El harness de tests (unitarios con I/O mockeado,
integración con Claude stub, caos con error inyectado a medio turno) debe existir antes de
tocar el rewrite de VAD/servidor de Fase 1 — no después. Ver [ADR-0006](./adr/0006-arquitectura-hexagonal.md).

## Escala

### NFR-11
**Concurrencia de diseño.** El sistema está dimensionado explícitamente para 1 sesión
concurrente en una sola ubicación/concesionario (ver GOALS.md, Alcance confirmado). Escalar más
allá de esto es un cambio de alcance explícito, no una extensión incremental — ver TODOS.md.

## Idioma

### NFR-12
**Entrenamiento en inglés.** La llamada se entrena y evalúa en inglés (reporte a policía en
USA) — STT (`language="en"`), TTS (`lang_code="a"`, inglés americano) y el system prompt del
dispatcher están configurados así. Soporte bilingüe no ha sido solicitado.
