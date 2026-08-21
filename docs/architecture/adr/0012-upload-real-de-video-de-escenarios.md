# ADR-0012: Upload real de video de escenarios (reemplaza la referencia manual de path de v1)

- **Status:** accepted — resuelto en la misma sesión de implementación, sobre feedback directo
  del usuario ("no tengo como subir un video ni crear un escenario con video") tras probar la v1
  descrita en [escenarios-de-video.md](../../designs/escenarios-de-video.md).
- **Date:** 2026-08-21
- **Deciders:** implementación directa (Claude Code), corrigiendo un recorte de alcance propio
  que resultó impracticable en el uso real, no solo teórico.

## Context and problem statement

El plan original (Scope Decision de escenarios-de-video.md) diferió el upload de video a
propósito para v1: el video se referenciaba por una ruta de archivo que un administrador
colocaba manualmente en el disco del servidor, y quien autora el escenario solo escribía esa
ruta en un campo de texto. Al usarlo de verdad, esto resultó no ser una opción real para el
usuario — no tiene manera de colocar archivos en el disco del servidor ni razón para tenerla
(es exactamente el tipo de tarea de infraestructura que un manager/no-técnico no debería
necesitar hacer a mano). El recorte de alcance, evaluado correctamente en el momento
("< 1 día, corta 2-3 archivos"), resultó ser el recorte equivocado en la práctica: sin upload,
la feature completa (escenarios de video) es inutilizable, no solo "menos pulida".

## Decision drivers

- El feedback es directo y concreto, no una preferencia — sin esto, ninguna otra parte de la
  feature (autoría de ground truth, gate pre-llamada, scoring) es alcanzable por el usuario real.
- Eng ya había señalado (hallazgo 4.3, escenarios-de-video.md) que un path de cliente sin
  validar es un vector de path traversal — un upload real con nombre de archivo generado por el
  servidor es estrictamente **más seguro** que la v1 manual, no un trade-off.
- Sin dependencia nueva si se puede evitar: no instalar ffmpeg/ffprobe/moviepy solo para leer la
  duración de un archivo — ver Decision abajo.

## Considered options

1. **Upload real vía multipart** (`POST /scenarios/{id}/video/upload`) — el archivo viaja en el
   request, el servidor lo guarda con un nombre opaco (UUID) en un directorio propio
   (`VIDEO_STORAGE_DIR`), calcula el checksum, e intenta detectar la duración automáticamente.
2. **Mantener v1 (referencia de path manual) y documentar que requiere acceso al servidor** —
   descartada: es exactamente lo que el usuario acaba de confirmar que no funciona.
3. **Upload real + duración vía ffprobe/ffmpeg** (dependencia de sistema nueva) — más preciso y
   soporta más formatos, pero agrega una dependencia de infraestructura (binario externo, no un
   paquete de Python) que no existe hoy en este repo y que el spike de Gate 0 ya mostró es
   sensible en esta máquina (CUDA/toolchain roto, ver TODO-08) — no es el momento de agregar otra
   dependencia de sistema sin evidencia de que el parser propio (opción 1) no alcance.

## Decision

Se elige la opción 1, con detección de duración vía un parser propio y mínimo del box
`moov/mvhd` del formato ISO base media (MP4/MOV) — `server/video_probe.py`, sin dependencia
nueva, solo la librería estándar (`struct`). Es best-effort a propósito: si el archivo no es un
MP4/MOV bien formado o el parser no encuentra `mvhd` donde lo espera (ej. MP4 fragmentado
atípico), devuelve `None` y el formulario de autoría pide la duración a mano — el mismo campo
manual de v1 se mantiene como fallback, no se eliminó, solo dejó de ser la única vía.

El archivo se guarda con un nombre generado por el servidor (`{uuid4()}{extensión}`) en
`VIDEO_STORAGE_DIR` (nuevo, default `./video_storage`), nunca con el nombre que mandó el
cliente — cierra el vector de path traversal que la v1 manual dejaba abierto (hallazgo Eng 4.3)
en vez de solo mantenerlo. Extensión limitada a un allowlist (`.mp4`, `.mov`, `.m4v`) — rechazo
explícito con 4xx de cualquier otra, no "aceptar y fallar después" (mismo criterio que el plan de
tests original ya pedía). Tamaño máximo configurable (`VIDEO_MAX_UPLOAD_BYTES`, default 2 GB) —
Eng 4.4 ya señalaba que ningún input de este repo tenía límite de tamaño; este es el primero que
lo necesita de verdad.

La opción 3 (ffprobe) queda documentada como mejora futura si el parser propio resulta
insuficiente en uso real (ej. muchos archivos no-MP4/MOV, o MP4 fragmentados donde el parser
falla seguido) — no se descarta, se difiere por falta de evidencia de que haga falta.

## Consequences

**Positive**
- Resuelve el bloqueo real reportado por el usuario — la feature completa vuelve a ser
  alcanzable sin acceso al filesystem del servidor.
- Mejora la postura de seguridad respecto a v1 (path opaco generado por el servidor, allowlist
  de extensión, límite de tamaño) en vez de solo mantenerla.
- Cero dependencias nuevas.

**Negative**
- El parser de duración es best-effort — no soporta todos los MP4 posibles (ej. `moov` al final
  del archivo en streaming progresivo raro, contenedores no-ISO-BMFF como `.avi`/`.mkv`). El
  fallback manual cubre esos casos, a costa de una entrada de formulario extra ocasional.
- Guardar archivos en disco local (`VIDEO_STORAGE_DIR`) sigue siendo almacenamiento de un solo
  servidor, sin replicación/backup — mismo perfil de riesgo que `sessions.db` ya tiene (NFR-11,
  una sola ubicación, un solo servidor).

**Risks**
- Si el volumen de escenarios de video crece mucho, `VIDEO_STORAGE_DIR` en el mismo disco que
  `sessions.db`/certificados TLS/pesos de Whisper-Kokoro puede necesitar moverse a un disco
  separado — no es un riesgo real hoy dado el alcance confirmado (NFR-11).

## Options not chosen

- **Mantener solo la referencia manual de v1 (opción 2)**: descartada — es el problema reportado,
  no una alternativa.
- **ffprobe/ffmpeg (opción 3)**: mejora futura documentada, no descartada, diferida por falta de
  evidencia de que el parser propio no alcance.
