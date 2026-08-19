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

## Backend

Requisitos: Python 3.12, uv, micrófono y altavoces.

```powershell
Copy-Item .env.example .env
# Configura las variables privadas solamente en el .env de la raíz.
uv sync
uv run python apps/voice-agent/src/server.py
```

El servicio escucha de forma predeterminada en `ws://127.0.0.1:8765`.

## Frontend

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
python -m unittest discover -s apps/voice-agent/tests -v
cd frontend
npm run build
```

Los datos de sesiones se guardan bajo `data/`, que está excluido del control de
versiones. Los secretos permanecen en el `.env` raíz, también excluido.
