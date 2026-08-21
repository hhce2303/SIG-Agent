# SIG Agent

Simulador de entrenamiento para operadores de llamadas de emergencia. El
repositorio separa explícitamente el frontend de escritorio y el backend de
voz para que ambos equipos puedan trabajar y desplegar de manera independiente.

## Estructura

```text
SIG-Agent-Backend/
├── frontend/          # Electron + React + TypeScript + Vite
├── apps/
│   └── voice-agent/   # Python + Whisper + Claude + Kokoro
├── pyproject.toml
└── uv.lock
```

El contrato que debe implementar el backend está en
`frontend/BACKEND_REQUIREMENTS.md`.

## Desarrollo local (backend + frontend juntos)

```powershell
.\dev-up.ps1
```

Levanta el backend real (`apps/voice-agent/src/server_main.py` — Whisper + Claude API + Kokoro
+ micrófono, sin stubs) y el frontend real (Electron + Vite) cada uno en su propia ventana de
PowerShell, con WSS/TLS real por default (certificado autofirmado, ver NFR-05). Requiere que el
`.env` de la raíz ya tenga `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `SESSION_TOKEN_SECRET` y
`SUPERVISOR_PASSPHRASE` (ver [ADR-0008](docs/architecture/adr/0008-mecanismo-de-autenticacion-de-sesion.md)).
`.\dev-up.ps1 -DisableTls` corre en texto plano solo para debug local;
`.\dev-up.ps1 -Stop` detiene ambos servicios. Ver comentarios del script para el detalle.

## Backend (manual, sin el script)

Requisitos: Python 3.12, `uv`, micrófono y altavoces.

```powershell
uv sync
cd apps/voice-agent/src
python server_main.py
```

El servicio escucha en `wss://127.0.0.1:8000` por default (`DISABLE_TLS=1` para texto plano en
desarrollo local). El punto de entrada real es `server_main.py`, no un `server.py` a nivel de
`apps/voice-agent/src` — ver [AGENTS.md](AGENTS.md) para el estado real del código vs. la
documentación de cada fase.

## Frontend (manual, sin el script)

Requisitos: Node.js 20 o superior y npm.

```powershell
cd frontend
Copy-Item .env.example .env
npm install
npm run dev
```

El frontend no inicia Python ni contiene claves privadas. El backend debe estar
ejecutándose por separado. Consulta `frontend/README.md` para configuración,
compilación y empaquetado.

## Validación

```powershell
cd apps/voice-agent
uv run pytest -q
cd ../../frontend
npm run build
```

Los secretos viven en el `.env` de la raíz (excluido de git). La sesión SQLite real se guarda
en `apps/voice-agent/src/sessions.db` (también excluido) — ver
[ADR-0007](docs/architecture/adr/0007-motor-de-persistencia.md).
