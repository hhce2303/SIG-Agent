# ADR-0013: Instalador Windows unificado para el perfil monomáquina actual

- **Status:** accepted
- **Date:** 2026-08-28
- **Deciders:** usuario, con revisión de implementación

## Context and problem statement

El Cliente Electron y el backend PyInstaller ya podían distribuirse sin Node ni Python, pero
como dos artefactos que el usuario debía instalar, configurar e iniciar por separado. Además, el
pipeline real de audio todavía abre el micrófono y los parlantes desde el proceso backend; por
eso ambos procesos deben correr hoy en el mismo equipo aunque ADR-0004 conserve como objetivo la
topología servidor LAN cuando exista audio por red.

Se necesita una sola instalación Windows que coloque ambos componentes, arranque el backend al
abrir el Cliente y preserve secretos, sesiones, certificados, logs y videos durante upgrades.

## Decision drivers

- NFR-11: una instalación operable sin conocimiento de Python, Node ni consolas de desarrollo.
- El backend empaquetado ocupa aproximadamente 1.73 GiB y sus modelos son assets de solo lectura.
- `.env`, SQLite, certificados, logs y videos no pueden vivir en una carpeta reemplazable.
- El backend debe estar saludable antes de que el Cliente intente autenticar o abrir WSS.
- Los secretos nunca entran al instalador ni al bundle Vite.

## Considered options

1. Seguir entregando ZIP de backend e instalador Electron por separado.
2. Incluir el backend como recurso de Electron y hacer que Electron gestione su proceso.
3. Instalar el backend como Windows Service.

## Decision

Se elige la opción 2 para el perfil monomáquina actual:

- Electron-builder/NSIS incluye el `--onedir` completo bajo `resources/backend`.
- Electron usa `%LOCALAPPDATA%\SIG Agent\data` como directorio persistente.
- Electron configura `SIG_AGENT_DATA_DIR`, inicia `server_main.exe`, espera
  `https://127.0.0.1:8000/health` y solo después crea la ventana del Cliente.
- En el primer arranque se copia `.env.example`; si faltan secretos, se abre el archivo y la
  aplicación sale sin intentar iniciar un backend inválido.
- Electron termina únicamente el backend que esa misma instancia inició. Un backend ya saludable
  iniciado por soporte puede reutilizarse y no se reclama como propio.
- La consola queda visible en esta primera entrega; `logs/server.log` sigue siendo persistente.

`bundle_dir()` continúa resolviendo modelos dentro del bundle PyInstaller. `base_dir()` acepta
el override `SIG_AGENT_DATA_DIR`; sin él conserva el comportamiento anterior, por lo que el ZIP
standalone sigue siendo un fallback compatible.

ADR-0004 no queda superseded: sigue siendo la topología objetivo condicionada al spike y a
construir audio por red. Este ADR registra el perfil realmente ejecutable mientras ese pipeline
no existe y no afirma que cambiar la URL del Cliente transporte audio.

## Consequences

**Positive**

- Un solo instalador y un solo acceso directo levantan ambos procesos.
- Una actualización de binarios/modelos no pisa estado ni secretos.
- La ventana no aparece hasta que el backend está listo.
- Se conserva el backend standalone como herramienta de soporte y rollback.

**Negative**

- El instalador supera 1 GiB y cada update unificado vuelve a transportar los modelos.
- Electron incorpora responsabilidad operativa sobre un proceso Python.
- La primera configuración aún requiere editar `.env`; no hay wizard de secretos.
- El backend visible en consola es funcional pero no es la UX final.

**Risks**

- El tamaño debe validarse con el NSIS real y suficiente espacio temporal en una máquina limpia.
- Un cierre forzado puede impedir el registro limpio de una sesión activa.
- El instalador sigue sin firma digital y SmartScreen puede advertir.

## Options not chosen

- **Dos artefactos:** ya funciona, pero conserva pasos manuales y permite versiones incompatibles.
- **Windows Service:** requiere decisiones de privilegios, cuenta de servicio, acceso al audio de
  sesión interactiva y upgrade; es prematuro para este perfil monomáquina.
