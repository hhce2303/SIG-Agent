# SIG Agent Frontend

Aplicación de escritorio de SIG Agent construida con Electron, React,
TypeScript y Vite. Esta carpeta es un proyecto frontend independiente: no
contiene Python, claves de proveedores de IA ni inicia procesos del backend.

## Requisitos

- Node.js 20 o superior.
- npm.
- Un backend compatible con el contrato de
  [`BACKEND_REQUIREMENTS.md`](./BACKEND_REQUIREMENTS.md).

## Configuración

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

La aplicación intenta conectarse a `ws://127.0.0.1:8765` de forma
predeterminada. Para usar otro entorno, modifica únicamente:

```dotenv
VITE_BACKEND_WS_URL=wss://api.example.com/voice
```

La URL también puede cambiarse durante la ejecución desde **Settings**. Ese
valor se guarda localmente en el equipo del usuario y tiene prioridad después
de guardarse.

## Comandos

```powershell
npm run dev         # Vite + Electron
npm run build       # validación TypeScript + bundle web
npm run dist:win    # instalador de Windows (local, sin publicar)
npm run release:win # instalador de Windows + publica el release en GitHub (requiere GH_TOKEN)
```

`npm run dev` inicia solamente el frontend. El equipo de backend debe ejecutar
su servicio por separado.

## Auto-update (Fase 3)

El cliente empaquetado (`app.isPackaged`, nunca en `npm run dev`) chequea
actualizaciones al arrancar y cada 4h contra los Releases de
`github.com/hhce2303/SIG-Agent` (repo público — los clientes no necesitan
token para leer). Para publicar una versión nueva:

1. Subir la versión en `package.json`.
2. Exportar `GH_TOKEN` (un token con permiso de subir assets a Releases —
   solo en la máquina que empaqueta el release, nunca en un cliente).
3. `npm run release:win`.

Los clientes ya instalados detectan el release nuevo, lo descargan, y lo
aplican al reiniciar la app (notificación nativa del sistema operativo, sin
diálogo custom).

## Límites de responsabilidad

El frontend se encarga de navegación, estado visual, configuración de la URL,
envío de comandos y renderizado de eventos. El backend se encarga del
micrófono, transcripción, IA, síntesis y reproducción de voz, escenarios,
evaluación y persistencia.

Ninguna clave secreta puede estar en esta carpeta. Vite publica en el bundle
todo valor cuyo nombre comience por `VITE_`.

## Estructura

```text
frontend/
├── electron/                # ventana de escritorio, sin lógica backend
├── src/
│   ├── components/
│   ├── lib/voiceBridge.ts   # transporte WebSocket
│   ├── pages/
│   ├── stores/
│   └── types.ts             # respuestas esperadas del backend
├── .env.example
├── BACKEND_REQUIREMENTS.md
└── package.json
```

## Integración

Antes de integrar una versión del backend, valida la lista de aceptación al
final de [`BACKEND_REQUIREMENTS.md`](./BACKEND_REQUIREMENTS.md). Los cambios
incompatibles del protocolo deben acordarse y versionarse antes de modificar
el frontend.
