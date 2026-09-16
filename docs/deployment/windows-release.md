# Entrega Windows — SIG Agent

La entrega normal usa **un solo instalador** que contiene Cliente y backend. El ZIP separado del
backend se conserva únicamente como fallback de soporte.

## Artefactos

- Instalador unificado: `frontend/release/SIG Agent Setup 0.1.0.exe`.
- Fallback backend: `apps/voice-agent/src/dist/SIG-Agent-Backend.zip`.
- Cada artefacto generado tiene un checksum SHA-256 al lado.

El backend y el cliente deben correr hoy en la **misma máquina**: el backend abre el micrófono y
los parlantes locales. La URL predeterminada del cliente (`wss://127.0.0.1:8000`) coincide con la
plantilla incluida. Cambiarla a una IP LAN no transmite audio desde el cliente; eso requiere el
pipeline de audio por red que todavía no existe.

## Instalación

1. Ejecutar `SIG Agent Setup 0.1.0.exe`. El instalador no está firmado; Windows SmartScreen
   puede pedir confirmación. No desactivar SmartScreen globalmente.
2. Abrir **SIG Agent**. En el primer arranque se crea y abre automáticamente
   `%LOCALAPPDATA%\SIG Agent\data\.env`.
3. Completar como mínimo `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `SESSION_TOKEN_SECRET` y
   `SUPERVISOR_PASSPHRASE`. Usar un secreto aleatorio de al menos 32 bytes para
   `SESSION_TOKEN_SECRET`; no reutilizarlo en otra instalación.
4. Guardar `.env` y volver a abrir **SIG Agent**. Electron iniciará el backend, esperará su
   health check y abrirá el Cliente. La consola queda visible por ahora.
5. Conservar `wss://127.0.0.1:8000`, ingresar el identificador del
   supervisor y la passphrase configurada.

## Actualización y rollback

El estado ya vive fuera de la instalación, en `%LOCALAPPDATA%\SIG Agent\data`:

- `.env`
- `sessions.db`
- `server.crt` y `server.key`
- `video_storage/`

Una actualización no debe borrar esa carpeta. No compartir certificados, bases de datos ni
`.env` entre concesionarios. Antes de un downgrade, hacer una copia por TODO-20.

## Reconstrucción

Desde la raíz del repo:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\build_release.ps1
```

El build del backend descarga los modelos solo en la máquina de build; la máquina destino no
necesita Python, Node, `uv` ni acceso a Hugging Face.
