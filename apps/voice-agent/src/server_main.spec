# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec para el ejecutable standalone del backend de voice-agent.

Ver docs/designs/empaquetado-ejecutable-backend.md (design doc completo, 3 rondas de revisión
adversarial + revisión de ingeniería) para el razonamiento detrás de cada decisión de este
archivo. Resumen de lo que importa mantener sincronizado si se toca este `.spec`:

- Invocar SIEMPRE desde `apps/voice-agent/src` (mismo cwd que usa `dev-up.ps1`) — los imports
  del proyecto son planos (`audio`, `auth`, `core`, ...) y dependen de ese cwd.
- `--onedir`, no `--onefile` (Recommended Approach del design doc): evita re-extraer varios
  cientos de MB de binarios nativos + pesos de modelo en cada arranque.
- `datas=[('../../../models', 'models')]` coloca `models/` dentro de `_internal/` — el código
  lo resuelve vía `bundle_dir()` (`sys._MEIPASS`), NUNCA vía `base_dir()` (Premisa 4 — confundir
  esos dos directorios fue un bug real encontrado en revisión, no una preocupación teórica).
- `console=True` es una decisión EXPLÍCITA (Premisa 8), no un default implícito — con consola
  visible por ahora; cambiar a `False` es una decisión de producto separada (UX de "doble-click
  silencioso" vs. poder ver el arranque), no algo que este `.spec` decida solo.
- La lista de `--collect-all` de abajo es EXACTAMENTE la de "The Assignment" en el design doc —
  si el build exploratorio revela hooks/imports faltantes adicionales, agregarlos acá con un
  comentario citando qué encontró el build, no adivinar de antemano.

Generar/actualizar este archivo con:
    cd apps/voice-agent/src
    uv run pyinstaller --collect-all faster_whisper --collect-all ctranslate2 \\
        --collect-all onnxruntime --collect-all kokoro --collect-all torch \\
        --collect-all transformers --collect-all av --collect-all sounddevice \\
        --collect-all soundfile --collect-all uvicorn --onedir --name server_main \\
        server_main.py
Luego editar el `Analysis(...)` generado para agregar el `datas` de `models/` de abajo (PyInstaller
no lo agrega solo) y confirmar `console=True`.
"""

from PyInstaller.utils.hooks import collect_all

COLLECT_ALL_PACKAGES = [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "kokoro",
    "torch",
    "transformers",
    "av",
    "sounddevice",
    "soundfile",
    "uvicorn",
    # Encontrado corriendo el .exe compilado de verdad, no un import-time warning de PyInstaller
    # (ver docstring de este archivo): `language_tags` es una dependencia transitiva de la
    # cadena de fallback de fonemización de kokoro (kokoro -> misaki -> phonemizer -> segments
    # -> csvw -> language_tags) y trae un archivo de datos propio (`data/json/index.json`) que
    # `--collect-all kokoro` NO arrastra -- `collect_all` de un paquete no recolecta los datos de
    # SUS dependencias transitivas, solo del paquete nombrado. Esto no aparece como error de
    # import en el build (PyInstaller SÍ encuentra el módulo `.py`), solo al arrancar el `.exe`
    # de verdad -- exactamente el tipo de gap que este build exploratorio existe para encontrar.
    "language_tags",
    # Mismo patrón: `espeakng_loader` (dependencia de `misaki.espeak`, la fonemización de
    # fallback de kokoro) trae su propio directorio de datos empaquetado (`espeak-ng-data`) que
    # `--collect-all kokoro` no arrastra. Hallazgo importante para el riesgo de espeak-ng que el
    # design doc dejaba como Open Question: NO hace falta un binario nativo de `espeak-ng`
    # instalado por separado en la máquina destino -- `espeakng_loader` ya es una dependencia de
    # pip que trae los datos necesarios, alcanza con `--collect-all`.
    "espeakng_loader",
]

datas = []
binaries = []
hiddenimports = []
for _pkg in COLLECT_ALL_PACKAGES:
    _datas, _binaries, _hiddenimports = collect_all(_pkg)
    datas += _datas
    binaries += _binaries
    hiddenimports += _hiddenimports

# Premisa 4: pesos de modelo (producidos por scripts/fetch_models.py, corrido ANTES de este
# build) — relativo a este .spec (apps/voice-agent/src/), models/ vive en la raíz del repo, tres
# niveles arriba. Termina en `_internal/models/` del build final; el código los lee vía
# `bundle_dir()` (`sys._MEIPASS`), no `base_dir()`.
datas += [("../../../models", "models")]

a = Analysis(
    ["server_main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Corrección real (encontrada corriendo el build de "The Assignment" de verdad, no adivinada de
# antemano — y en un segundo intento: filtrar la lista `datas` ANTES de `Analysis()` no alcanza,
# porque los hooks propios de PyInstaller vuelven a agregar los datos de `torch` de forma
# independiente durante el análisis — hay que filtrar `a.datas`, después de que `Analysis` corrió,
# no antes). `torch-*.dist-info/licenses/third_party/kineto/libkineto/third_party/dynolog/...`
# son textos de licencia de dependencias de profiling GPU que este proceso CPU-only, un solo
# proceso, jamás importa -- pero su anidamiento es tan profundo que la ruta final revienta el
# límite clásico de 260 caracteres de Windows (`WinError 206`) en cuanto el repo vive bajo una
# ruta moderadamente larga (ej. sincronizada con OneDrive, como este mismo repo). Se excluyen
# del bundle en vez de depender de que cada máquina de build tenga long-path support habilitado
# (`LongPathsEnabled` en el registro) -- eso requeriría privilegios de admin, no garantizados en
# una máquina de concesionario. Solo se excluye `licenses/`, nunca el resto de `dist-info/`
# (`METADATA`/`RECORD` sí importan si algo hace `importlib.metadata.version(...)` en runtime).
a.datas = [
    d for d in a.datas
    if not ("dist-info" in d[0].replace("\\", "/") and "/licenses/" in d[0].replace("\\", "/"))
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="server_main",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # Decisión explícita (Premisa 8) — ver docstring de este archivo. `core.observability`
    # guarda `sys.stdout is not None` antes de agregar el StreamHandler, así que un cambio a
    # `console=False` más adelante no rompe el logging — solo pierde las líneas de stdout (el
    # file handler de `logs/server.log` sigue funcionando igual).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="server_main",
)
