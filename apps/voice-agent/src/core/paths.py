"""Resolución de rutas para el ejecutable empaquetado (PyInstaller) — ver
docs/designs/empaquetado-ejecutable-backend.md, Premisas 4 y 6.

Dos categorías de rutas, dos helpers — nunca la misma función para ambas, ese error
(conflacionar ambos directorios) fue un hallazgo real de la revisión de ingeniería, no una
preocupación teórica:

- `base_dir()`: estado ESCRIBIBLE. Si `SIG_AGENT_DATA_DIR` está configurada, resuelve a ese
  directorio externo (perfil del instalador unificado); de lo contrario se mantiene anclado
  junto al ejecutable (`.env`, `sessions.db`, `logs/`, certificados TLS, `video_storage/`).
  Bajo PyInstaller `--onedir` el `.exe` vive en `dist/<name>/`, junto a `_internal/`.
- `bundle_dir()`: assets de SOLO LECTURA empaquetados vía `datas=[]` (pesos de modelo).
  PyInstaller coloca esos archivos dentro de `_internal/` (o del directorio de descompresión
  temporal en modo onefile) y expone esa ruta en tiempo de ejecución como `sys._MEIPASS`.

En desarrollo (no frozen) ambos resuelven al mismo lugar: el directorio raíz de `src/` (donde
vive `server_main.py`), calculado en base a la ubicación de este propio archivo
(`core/paths.py` → padre de `core/` → `src/`), no del CWD desde el que se invoque pytest/uvicorn
— eso es justamente lo que hace a estos helpers independientes de CWD tanto en frozen como en
dev.
"""

import os
import sys


def _dev_root() -> str:
    # apps/voice-agent/src/core/paths.py -> apps/voice-agent/src/
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def base_dir() -> str:
    """Directorio de estado escribible, con override explícito para el instalador unificado."""
    configured_data_dir = os.getenv("SIG_AGENT_DATA_DIR")
    if configured_data_dir:
        return os.path.abspath(os.path.expandvars(os.path.expanduser(configured_data_dir)))
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _dev_root()


def bundle_dir() -> str:
    """Directorio de assets empaquetados de solo lectura (modelos): `sys._MEIPASS` bajo
    PyInstaller, `src/` en desarrollo (no hay bundle — se resuelve igual que `base_dir()`)."""
    return getattr(sys, "_MEIPASS", _dev_root())
