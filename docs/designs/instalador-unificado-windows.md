# Design: instalador Windows unificado de SIG Agent

## Resultado

`build_release.ps1` produce un instalador NSIS único. Contiene el Cliente Electron y el backend
PyInstaller completo; la máquina destino no necesita Python, Node, `uv`, npm ni acceso a Hugging
Face. La decisión estructural está en ADR-0013.

## Layout

```text
<directorio de instalación>/
  SIG Agent.exe
  resources/backend/
    server_main.exe
    .env.example
    _internal/models/

%LOCALAPPDATA%/SIG Agent/data/
  .env
  sessions.db
  server.crt
  server.key
  logs/server.log
  video_storage/
```

Los modelos son de solo lectura y viajan con cada versión. El segundo árbol es persistente y no
debe entrar al instalador, auto-update ni desinstalación silenciosa.

## Secuencia de arranque

```text
SIG Agent.exe
  -> single-instance lock
  -> crear data/
  -> copiar .env.example si .env no existe
  -> validar cuatro variables requeridas sin imprimir valores
  -> si faltan: abrir .env y salir
  -> si /health ya responde: reutilizar backend externo
  -> iniciar resources/backend/server_main.exe con SIG_AGENT_DATA_DIR
  -> esperar /health hasta 120 s
  -> abrir la ventana Electron
```

Al salir, Electron termina solo el backend que inició. El modo desarrollo continúa iniciando
solo el frontend para no cambiar `npm run dev`.

## Build

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
```

El script ejecuta `build_exe.ps1 -SkipArchive`, valida `server_main.exe`, corre
`npm.cmd run dist:win` y genera el SHA-256. `frontend/package.json::extraResources` es la fuente
de verdad del lugar donde entra el backend.

Después de validar el backend una vez, `build_release.ps1 -SkipBackend` permite iterar solo sobre
Electron/NSIS. `SIG_AGENT_PACKAGED_SMOKE_TEST=1` hace que el Cliente empaquetado valide
spawn -> `/health` -> shutdown sin abrir la ventana; es un mecanismo de build, no configuración
de producción.

## Fallos visibles

- `.env` incompleto: diálogo con nombres faltantes y apertura del archivo.
- Backend ausente: diálogo con la ruta esperada.
- Salida temprana o timeout: diálogo y ruta de `logs/server.log`.
- Puerto ocupado por un SIG Agent saludable: se reutiliza y no se termina al salir.
- Puerto ocupado por otro proceso: el backend falla y su log/consola conserva el diagnóstico.

## Criterios de aceptación

- Un solo instalador funciona en Windows limpio sin toolchains de desarrollo.
- El instalador no contiene `.env`, claves privadas, SQLite ni videos de la máquina de build.
- Frontend no abre antes de que `/health` responda 200.
- Login WSS y un turno push-to-talk STT -> Claude -> TTS funcionan con audio real.
- Reinicio y upgrade conservan `.env`, SQLite, certificado y videos.
- Cerrar la app no deja el backend que ella inició escuchando en el puerto 8000.
- La advertencia real de SmartScreen y el espacio temporal requerido quedan registrados.

## Rollback

Conservar el instalador anterior. Como los datos están fuera de la instalación, reinstalar una
versión anterior no requiere copiar `.env` o SQLite. Un downgrade que cambie schema seguirá
requiriendo una política explícita de migraciones (TODO-20).
