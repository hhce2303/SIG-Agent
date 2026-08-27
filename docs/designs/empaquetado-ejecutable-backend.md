# Design: Empaquetado del backend de voice-agent como ejecutable standalone

Generado por /office-hours (invocado inline desde /autoplan) el 2026-08-24
Branch: feature/video-scenarios
Repo: hhce2303/SIG-Agent
Status: APPROVED
Mode: Startup (intrapreneurship — infra interna, no requiere validación de demanda)

## Problem Statement

`apps/voice-agent` (Python 3.12, FastAPI + uvicorn) solo corre hoy desde un venv gestionado con
`uv` (`pyproject.toml` + `uv.lock`, sin `requirements.txt`). Levantarlo en una máquina nueva
requiere Python 3.12, `uv sync`, y una sesión de shell que sepa activar el venv y correr
`server_main.py` — inviable para distribuir a la caja LAN de un concesionario (NFR-11: una sola
ubicación, sin soporte de TI dedicado). Pedido textual: "construyamos un ejecutable... hay que
agregarle las dependencias y requerimientos en el ejecutable" (PyInstaller mencionado como
ejemplo de herramienta). Se necesita un ejecutable standalone que empaquete el intérprete, todas
las dependencias (`anthropic`, `cryptography`, `fastapi`, `faster-whisper`, `kokoro`, `numpy`,
`python-dotenv`, `python-multipart`, `sounddevice`, `soundfile`, `uvicorn[standard]`) y los
assets nativos que esas librerías requieren, de forma que la máquina destino no necesite Python
instalado. `kokoro` depende de `torch`/`transformers` (no `onnxruntime` — corrección de una
versión anterior de este doc: `onnxruntime` es en realidad dependencia de `faster-whisper`, para
su VAD Silero, `vad_filter=True` en `stt/whisper.py`), y `faster-whisper` a su vez depende de
`av` (PyAV, trae FFmpeg nativo). `torch`/`transformers` son, por tamaño y por su historial de
fragilidad con PyInstaller (branching CPU/CUDA, DLLs de backend), un riesgo de bundling mayor
que `sounddevice`/`soundfile`.

## Constraints

- **Este plan es una pieza parcial, no el despliegue completo.** `frontend/BACKEND_REQUIREMENTS.md`
  §2 exige que el backend corra en la MISMA máquina que tiene micrófono y parlantes
  (`KokoroTTS.speak()` usa `sd.play()`/`sd.wait()` locales, `MicrophoneRecorder` abre un
  `sd.InputStream` local) — la caja del concesionario necesita el frontend Electron corriendo
  también, no solo este ejecutable. Empaquetar el backend, aunque salga perfecto, no por sí solo
  produce "un training simulator funcionando en un concesionario sin soporte de TI." El empaquetado
  del frontend queda como trabajo de seguimiento explícito (TODO-21), no implícitamente resuelto.
- Solo cubre `apps/voice-agent` (backend Python). El frontend Electron/Vite es un empaquetado
  aparte y queda fuera de este plan.
- Dos entry points coexisten hoy: `server_main.py` (servidor real, uvicorn) y `main.py`
  (prototipo CLI, fallback manual de NFR-03). El pedido es "un ejecutable" — se empaqueta
  `server_main.py` únicamente; `main.py` sigue corriendo solo desde fuente.
- `faster-whisper` (vía ctranslate2) y `kokoro` (vía torch/transformers) descargan pesos de
  HuggingFace la primera vez que se instancian — hoy no hay ningún mecanismo de bundling.
- `sounddevice` (PortAudio), `soundfile` (libsndfile), `ctranslate2`, `onnxruntime`, `torch` y
  `av`/PyAV traen binarios nativos por wheel — no son paquetes puros de Python, PyInstaller
  necesita colectarlos explícitamente.
- `kokoro`'s fonemización (`misaki[en]`) cae a `espeak-ng` para palabras fuera de diccionario —
  en un simulador de despacho policial, nombres propios, calles y placas deletreadas SON el
  contenido de entrenamiento (mismo dato que `WhisperSTT` ya marca como crítico vía
  `[unclear: ...]`, ver `stt/whisper.py`), así que este no era un riesgo a tomar a la ligera.
  **Resuelto por "The Assignment" corrido de verdad:** `espeakng_loader` (dependencia de pip de
  `misaki.espeak`, no un binario nativo aparte que instalar) ya trae los datos de espeak-ng
  necesarios — `--collect-all espeakng_loader` alcanza, ver hallazgos reales en "The Assignment".
- Los secretos (`ANTHROPIC_API_KEY`, `SESSION_TOKEN_SECRET`, `SUPERVISOR_PASSPHRASE`,
  `MANAGER_PASSPHRASE`) NUNCA deben quedar embebidos en el ejecutable — se siguen resolviendo
  desde un `.env` externo, junto al ejecutable, en tiempo de ejecución.
- Plataforma objetivo: Windows (la caja del concesionario corre Windows, ver `dev-up.ps1`).

## Premises

1. Un solo ejecutable (`server_main.py`) es el objetivo — `main.py` (CLI) queda fuera de alcance
   sin pedido explícito. — ACORDADO
2. `WHISPER_MODEL_PATH` existe en `.env.example` pero es dead code: el default vive en
   `stt/whisper.py:29` (`model_size: str = "small"`), y el valor real usado en producción se
   vuelve a hardcodear en el call site, `server_main.py:90`
   (`WhisperSTT(model_size="small", ...)`), que pisa cualquier default de `whisper.py`. Conectar
   la variable exige tocar ambos puntos, no solo el default. Es parte de este trabajo, no scope
   creep — "empaquetar dependencias" exige una ruta local real a los pesos del modelo. —
   ACORDADO
3. **Kokoro necesita el mismo tratamiento que Whisper, pero es más grande** — hoy no tiene ni
   siquiera una variable muerta equivalente. `tts/kokoro.py:16-19` llama
   `KPipeline(lang_code=lang_code, repo_id="hexgrad/Kokoro-82M")` sin `model=`, lo cual dispara
   `hf_hub_download` internamente para `config.json` y los pesos `.pth` (ver
   `kokoro/pipeline.py`/`model.py` instalados en `.venv`). Además, `speak()` pasa el voice id
   (`KOKORO_VOICE`, ej. `"am_michael"`) directo a `load_single_voice()`, que TAMBIÉN llama
   `hf_hub_download` salvo que el string termine en `.pt` (ruta local). Este es el mismo gap que
   la Premisa 2 ya aceptó como en-scope para Whisper — se acepta bajo la misma justificación, no
   como creep nuevo: construir un `KModel(repo_id=..., config=<config.json local>,
   model=<.pth local>)` en build/arranque, pasarlo a `KPipeline(model=kmodel, ...)`. Contrato de
   variables: `KOKORO_MODEL_DIR` (nueva) apunta al directorio con `config.json`+`.pth`;
   `KOKORO_VOICE` **conserva su significado actual** (un voice id corto, ej. `am_michael` — no
   cambia `.env.example`), y el código resuelve la ruta `.pt` real como
   `<KOKORO_MODEL_DIR>/voices/<KOKORO_VOICE>.pt` en vez de pasarle el id crudo a
   `load_single_voice()`. Sin esto, el Success Criterion de "cero llamadas de red salientes" no
   es alcanzable — es un riesgo de feasibility real, no un detalle menor: como es una llamada de
   red en runtime (no un import faltante), no aparece como error de build — falla
   silenciosamente solo en la caja realmente offline del concesionario, en medio de la
   reproducción de audio. — ACORDADO
4. Los pesos de Whisper y Kokoro se descargan en build-time y quedan embebidos en el paquete —
   el ejecutable debe correr con cero acceso a internet en la máquina destino, sin descarga en el
   primer arranque. Mecanismo concreto: un script (`scripts/fetch_models.py`, corrido una vez
   antes del build) descarga los pesos a un directorio fijo `models/whisper/`, `models/kokoro/`
   — **no versionado en git** (los binarios de Whisper `model.bin` y el `.pth` de Kokoro superan
   holgadamente el límite de 100MB por archivo de GitHub; `models/` se agrega a `.gitignore` junto
   con `dist/`/`build/` — las carpetas de salida de PyInstaller, mismo riesgo de commitear
   binarios de varios GB por accidente — y se regenera localmente antes de cada build, igual que
   hoy se hace `uv sync`). Layout esperado bajo `models/kokoro/`: `config.json` + el `.pth` del
   modelo base (nombre según `KModel.MODEL_NAMES[repo_id]`) en la raíz, y `voices/<voice>.pt` por
   cada voz — `fetch_models.py` descarga únicamente la voz configurada en `KOKORO_VOICE` al
   momento del build, no el catálogo completo de voces de Kokoro (cambiar de voz más adelante
   requiere volver a correr el fetch para la voz nueva). Layout de `models/whisper/`: el
   directorio que produce `faster_whisper.download_model(model_size, output_dir=...)` — un
   snapshot CTranslate2 completo que `WhisperModel(local_dir, ...)` acepta directamente, sin
   transformación adicional.

   **Corrección crítica de una versión anterior de este doc:** el `.spec` de PyInstaller declara
   `models/` en `datas=[]`, pero eso NO lo coloca junto al `.exe` — PyInstaller ≥6 en modo
   `--onedir` pone todo lo declarado en `datas=[]`/`binaries` dentro de `dist/server_main/_internal/`,
   y solo el `.exe` queda directamente al lado de esa carpeta. `base_dir()` (Premisa 6,
   `os.path.dirname(sys.executable)`) resuelve al directorio que CONTIENE `_internal/`, no a
   `_internal/` en sí — no es la misma ruta que donde realmente queda `models/`. Por eso se
   define un segundo helper, `bundle_dir()`, específico para assets de solo lectura empaquetados
   vía `datas=[]`: `getattr(sys, "_MEIPASS", <directorio del script>)` — PyInstaller setea
   `sys._MEIPASS` en runtime apuntando exactamente a `_internal/` (o al directorio de
   descompresión en modo onefile). `WHISPER_MODEL_PATH`/`KOKORO_MODEL_DIR` se resuelven vía
   `bundle_dir()`, nunca vía `base_dir()` — son dos helpers para dos categorías de rutas
   distintas (solo-lectura-empaquetada vs. escribible-junto-al-exe), no el mismo helper
   reutilizado. — ACORDADO
5. Los binarios nativos requieren colección explícita en PyInstaller, no solo hooks de import:
   `sounddevice`/`soundfile` (PortAudio/libsndfile), `ctranslate2` (motor de inferencia de
   faster-whisper), `onnxruntime` (VAD Silero de faster-whisper, `vad_filter=True`), `torch`
   (backend de Kokoro — el mayor riesgo de bundling del grupo por historial de fragilidad con
   PyInstaller, aunque no necesariamente por tamaño — ver corrección de tamaño abajo), y `av`/PyAV
   (dependencia de faster-whisper, trae FFmpeg nativo). `uvicorn[standard]` además usa resolución
   de imports dinámica basada en strings (selección de loop/protocolo — h11 vs httptools,
   websockets, lifespan) — mismo riesgo de "falta un hook" aunque no sea nativo/binario. Corre en
   un solo proceso sin `workers=` (`uvicorn.run(app, ...)` con un objeto app, no un string, ver
   `server_main.py`) — evita la trampa clásica de PyInstaller+`multiprocessing`; si alguien agrega
   `workers>1` más adelante, eso reintroduce la necesidad de `multiprocessing.freeze_support()` en
   Windows y NO fallaría en build-time, solo en runtime (servidores duplicados o cuelgues
   silenciosos) — nota dejada como tripwire en los comentarios del `.spec`.

   **Corrección de tamaño (una versión anterior de este doc sobrecorrigió hacia "varios GB"):**
   los wheels Windows (`win_amd64`) fijados en `uv.lock` son: `torch` ~122MB, `av` ~27.6MB,
   `ctranslate2` ~19MB, `onnxruntime` ~13.7MB, `transformers` ~11.7MB (Python puro) — combinados,
   bajo 200MB. Las dependencias CUDA de `torch` (`nvidia-cudnn-cu13`, `triton`, etc.) están todas
   con marker `sys_platform == 'linux'` — no se instalan en Windows. El estimado original
   "~1-2GB" (dominado por los pesos de modelo embebidos, no por las librerías nativas en sí)
   parece más preciso que la revisión que lo reemplazaba — se confirma con la medición real de
   "The Assignment". — ACORDADO
6. Las rutas de certificado TLS, SQLite (`sessions.db`), `video_storage/`, **y el propio
   `.env`** se anclan al directorio del propio ejecutable, no al CWD desde el que se lo invoque
   (hoy todas son relativas al CWD vía `os.getenv(default=...)` y `load_dotenv()`, lo cual es
   fragil una vez empaquetado). Se incluye `.env` explícitamente aquí porque es la ruta más
   sensible del diseño — es donde viven los secretos que la Premisa 9 exige mantener fuera del
   binario — dejarla exenta de este mismo fix sería inconsistente. Implementación: un helper
   `base_dir()` que resuelve `os.path.dirname(sys.executable)` cuando `getattr(sys, "frozen",
   False)` es cierto, y el directorio del script en caso contrario; todos los `os.getenv(...,
   default_relativo)` pasan por él.

   **Cuidado con `.env` en dev (no solo frozen) — hallazgo de la fase de Eng review:**
   `dev-up.ps1` guarda `.env` en la RAÍZ del repo, pero lanza el backend con
   `-WorkingDirectory apps\voice-agent\src` — hoy esto funciona solo porque `load_dotenv()` sin
   argumentos hace una búsqueda hacia arriba desde el frame que lo llama. Si se fuerza
   `load_dotenv(dotenv_path=os.path.join(base_dir(), ".env"))` incondicionalmente, se rompe ese
   flujo de dev (dos niveles por debajo de donde vive `.env` hoy). Además, la búsqueda implícita
   de `load_dotenv()` es directamente poco confiable bajo PyInstaller: camina hacia arriba desde
   el `co_filename` del frame llamante, que en código congelado conserva la ruta de la MÁQUINA DE
   BUILD, no la de la máquina destino — falla en silencio, sin excepción. Por eso el fix real es
   condicional, no un solo `load_dotenv()`: en modo frozen (`sys.frozen`), pasar
   `dotenv_path=os.path.join(base_dir(), ".env")` explícito; en modo no-frozen (dev), dejar el
   `load_dotenv()` sin argumentos tal cual está hoy, sin tocarlo — nunca depender de la búsqueda
   implícita en el camino frozen. — ACORDADO
7. Si `.env` falta o le faltan variables requeridas (`ANTHROPIC_API_KEY`, `CLAUDE_MODEL`,
   `SESSION_TOKEN_SECRET`, `SUPERVISOR_PASSPHRASE`) en la máquina destino, el arranque debe
   fallar con un mensaje claro (qué variable falta, dónde va el `.env`) y salir con código
   distinto de cero — no un `KeyError` con traceback crudo de Python, inadmisible para personal
   sin soporte de TI dedicado (NFR-11).

   **Variable presente pero vacía — hallazgo de Eng review, gap real.** Todo call site relevante
   usa `os.getenv(key, default)`, que solo devuelve `default` cuando la clave está AUSENTE — si
   `.env` trae `WHISPER_MODEL_PATH=` (vacío), `os.getenv` devuelve `""`, no el default. El propio
   `.env.example` del repo ya deja `WHISPER_MODEL_PATH=`/`ANTHROPIC_API_KEY=`/`CLAUDE_MODEL=` en
   blanco — exactamente el patrón que alguien en el concesionario copiaría y dejaría así. El fix
   (aplicado a la vez que se tocan estos call sites para el anclaje de rutas): usar
   `os.getenv(key) or default`, no `os.getenv(key, default)`, en todos los puntos de esta
   premisa y de la Premisa 6. — ACORDADO
   **Validación de rutas de modelo al arranque, no en medio de una llamada — hallazgo de Eng
   review.** El mismo gate de fail-fast se extiende a `WHISPER_MODEL_PATH` y a la ruta resuelta
   `<KOKORO_MODEL_DIR>/voices/<KOKORO_VOICE>.pt` (Premisa 3): si no existen, fallar al arranque
   con mensaje claro, no dejar que `speak()`/`transcribe()` fallen silenciosamente en medio de una
   llamada de entrenamiento en vivo — el mismo estándar que ya aplica a los secretos. — ACORDADO
8. **Diagnóstico de campo — esto es un cambio de código, no solo documentación.**
   `core/observability.py::configure_logging()` hoy solo escribe JSON a `sys.stdout` — en un
   `.exe` de doble-click sin consola visible, ese output se pierde. Se agrega un file handler que
   escribe a `<base_dir()>/logs/server.log` (mismo helper de anclaje de rutas de la premisa 6),
   rotado por tamaño para no crecer sin límite. Si crear/escribir ese archivo falla (`OSError` —
   disco lleno, permisos bloqueados en una máquina de concesionario endurecida), el setup cae de
   vuelta a solo-stdout en vez de tirar abajo el arranque completo — una app corriendo sin log de
   archivo es mejor que ninguna app. Guardrail explícito para quien toque este handler más
   adelante: nunca loguear el valor de un secreto (`ANTHROPIC_API_KEY`, `SESSION_TOKEN_SECRET`,
   `SUPERVISOR_PASSPHRASE`, `MANAGER_PASSPHRASE`) — hoy nada los loguea, pero no hay ningún
   guardrail automático que lo impida si alguien agrega un log line de debug más adelante. El
   "runbook" para personal no técnico es entonces honesto: "si la app no arranca, comprimí la
   carpeta `logs/` de al lado del .exe y mandala."

   **Consola vs. modo ventana — decisión explícita, no un efecto secundario implícito.**
   `configure_logging()` usa `logging.StreamHandler(sys.stdout)`. Si el `.spec` se construye con
   `console=False` (necesario para que sea un doble-click silencioso sin ventana de consola,
   implícito en el propio framing de esta premisa), `sys.stdout` puede ser `None` bajo
   PyInstaller — pasarlo explícito a `StreamHandler(None)` no cae a stderr como cuando se omite
   el argumento, así que esas líneas se pierden en silencio (no crashea, `emit()` las descarta).
   El `.spec` debe fijar `console=True` o `console=False` como decisión explícita, y el handler de
   stdout debe agregarse condicionalmente (`if sys.stdout is not None`) para no hacer I/O inútil
   en cada línea de log bajo modo ventana. — ACORDADO
9. Los secretos se mantienen fuera del binario compilado — se siguen inyectando vía `.env`
   externo junto al ejecutable (ver premisa 6 sobre por qué `.env` también se ancla al
   directorio del ejecutable). Esto no es solo buena práctica: el bytecode de PyInstaller es
   trivialmente decompilable, así que este boundary es la única protección real — no hay
   fallback de ofuscación si más adelante alguien se tienta a hardcodear una clave "temporal"
   por conveniencia. — ACORDADO

## Approaches Considered

### Approach A: PyInstaller --onefile
Effort: M/L | Risk: Med-High
- Un solo archivo .exe con todo adentro.
- Pros: lo más simple de entregar ("corré este archivo"); no hay carpeta de internals visible.
- Cons: se auto-extrae a un directorio temporal en CADA arranque (pesos de Whisper/Kokoro +
  binarios de ctranslate2/onnxruntime/torch/PortAudio/av, del orden de ~1-2GB dominado por los
  pesos de modelo — ver corrección de tamaño en Premisa 5, tamaño real a confirmar en "The
  Assignment") — arranque lento, más superficie de falla, y un hook faltante es más difícil de
  diagnosticar porque nada es visible hasta que se desempaqueta.

### Approach B: PyInstaller --onedir
Effort: M | Risk: Med
- Un .exe junto a una carpeta `_internal/` con los binarios nativos y los pesos embebidos.
- Pros: arranque rápido (no hay re-extracción del orden de ~1-2GB en cada corrida), los archivos
  de modelo/certificado quedan visibles e intercambiables sin recompilar, más fácil de
  diagnosticar cuando falta algo.
- Cons: es un exe + carpeta, no un solo archivo — se distribuye/zippea la carpeta completa, no
  un único .exe.

### Approach C (lateral): Python portable + uv, sin PyInstaller
Effort: S/M | Risk: Low
- Empaquetar el build standalone de Python de `uv` + un venv congelado (`uv sync --frozen`) junto
  a un launcher delgado (.bat), en vez de compilar.
- Pros: evita por completo la fragilidad de los hooks de binarios nativos de PyInstaller (el
  riesgo más grande de A/B); mucho más rápido de dejar funcionando.
- Cons: no es un ejecutable compilado en sentido estricto — es un intérprete portátil + carpeta
  de venv + launcher, lo cual puede no satisfacer el pedido de "un ejecutable" si se necesita
  específicamente un binario compilado.
- Variante considerada y no elegida: envolver este mismo Python portátil + venv congelado en un
  instalador Windows real (Inno Setup/MSI) — daría experiencia "doble-click setup.exe" sin el
  riesgo de bundling nativo de PyInstaller. Se descarta por ahora porque PyInstaller fue la
  herramienta sugerida en el pedido original (ver Problem Statement), no por una limitación
  técnica de la variante en sí — queda anotado para la validación de TODO-22.

## Recommended Approach

**Approach B (PyInstaller --onedir).** PyInstaller fue la herramienta sugerida en el pedido
original; entre sus dos modos (onefile/onedir), onedir es la opción operativamente más segura
para un proyecto con dependencias nativas de ML pesadas (whisper/kokoro/torch/sounddevice):
evita el costo de re-extraer el bundle completo en cada arranque y deja los archivos de modelo
inspeccionables sin recompilar — importante en una caja de concesionario sin soporte de TI
dedicado, donde poder ver qué hay en la carpeta importa más que tener un solo archivo.

## Open Questions

- ¿El certificado TLS autofirmado se regenera con el `common_name` default
  (`voice-agent.local`) o el concesionario necesita uno específico? (No bloquea este plan —
  `TLS_CERT_PATH`/`TLS_KEY_PATH` ya son configurables.)
- ¿Se necesita firmar el ejecutable (code signing) para evitar advertencias de SmartScreen en
  Windows? Fuera de alcance de este plan salvo pedido explícito — pero el comportamiento real de
  SmartScreen contra el `.exe` sin firmar SÍ se prueba como parte de "The Assignment" (build
  exploratorio en una máquina Windows limpia, no solo en la máquina de desarrollo) — para una
  audiencia sin soporte de TI dedicado, "Windows protegió tu PC" puede ser un bloqueador de
  adopción real, no una nota al pie. Si aparece, escalar a decisión go/no-go antes del primer
  despliegue real, no dejarlo como sorpresa de campo.
- ~~¿Vale la pena bundlear el binario nativo `espeak-ng`...?~~ **RESUELTO** por "The Assignment"
  corrido de verdad: `espeakng_loader` (dependencia de pip de `misaki.espeak`) ya trae los datos
  de espeak-ng necesarios — alcanza con `--collect-all espeakng_loader` (ver hallazgos reales
  arriba). No hace falta instalar ni bundlear un binario nativo aparte.
- **Procedimiento de actualización (pre-deployment task, no ya un Open Question sin dueño).**
  Approach B (onedir) deja `sessions.db`, `video_storage/`, y el certificado TLS junto al `.exe` —
  sobreescribir la carpeta completa en una actualización los destruiría. Antes del PRIMER redeploy
  real (no antes de este PR): documentar el paso de copiar esos tres paths fuera de `_internal/`
  antes de reemplazar la carpeta, y de vuelta después. Dueño: quien ejecute ese primer redeploy —
  TBD hasta que exista una fecha de despliegue real; este plan no puede asignar un nombre a un
  evento sin fecha, pero el paso queda escrito acá para que no se improvise en el momento.
- ¿Cuál es el mecanismo físico para llevar el artefacto (varios GB, ver Premisa 5) a la máquina
  del concesionario? Este plan documenta las restricciones (sin dependencia de internet en el
  destino, verificar integridad con checksum) pero NO elige el mecanismo (USB, share de red LAN,
  disco externo) — es una decisión operativa del despliegue real, fuera del control de este
  código. Ver TODO-23.

## Success Criteria

- `apps/voice-agent/src/dist/server_main/server_main.exe` arranca en una máquina Windows limpia
  (sin Python, sin `uv`, sin acceso a internet) y responde `200` en `/health`.
- Los pesos de Whisper y Kokoro cargan desde archivos embebidos junto al ejecutable — cero
  llamadas de red salientes a HuggingFace en el arranque.
- `sessions.db`, `server.crt`/`server.key`, y `video_storage/` se crean junto al ejecutable
  (no en el CWD desde el que se lo invoque).
- El build es reproducible desde `uv.lock` — un `.spec` de PyInstaller versionado en el repo, no
  un build manual ad hoc.
- Un smoke test end-to-end offline (audio de prueba fijo → `WhisperSTT.transcribe()` →
  `KokoroTTS.speak()`) corre contra el `.exe` compilado y produce audio real — no solo arranque y
  `/health`. Import-time analysis (lo que valida "The Assignment") no detecta fallos de carga de
  binarios nativos en tiempo de inferencia (ctranslate2/onnxruntime), así que este criterio es el
  que realmente cierra ese gap.
- `<base_dir()>/logs/server.log` existe y contiene las líneas de arranque después de correr el
  `.exe` con la consola cerrada — confirma que el diagnóstico de campo (premisa 8) funciona sin
  depender de una ventana de consola visible.
- El `.exe` se lanza desde un CWD distinto al de su propia carpeta (ej. `cmd /c "C:\Otro> ruta\a\
  server_main.exe"`) y arranca igual — el punto entero de `base_dir()`/`bundle_dir()` es
  independencia de CWD; un smoke test que siempre hace `cd` a la carpeta del exe antes de correrlo
  puede pasar mientras esconde exactamente el bug que este plan existe para arreglar.

**Notas de testing (detalle completo en la fase de Eng Review, Section 3):** unit tests para
`base_dir()`/`bundle_dir()` bajo `sys.frozen` simulado (barato, corre en CI, no depende de un
build real); test del fail-fast de la Premisa 7 distinguiendo ".env ausente" de "variable vacía"
(gap real, ver Premisa 7); test del fallback de logging ante `OSError` (Premisa 8).

## Distribution Plan

- `uv sync` corre desde la raíz del repo (`pyproject.toml`/`uv.lock` son a nivel monorepo — no
  existe un `pyproject.toml` anidado en `apps/voice-agent`); esto instala `pyinstaller` porque se
  agrega como dev-dependency en el `pyproject.toml` raíz (ver Dependencies).
- Build local por ahora: script (`build_exe.ps1`) en la raíz del repo cuya secuencia literal es:
  `uv sync` (raíz) → `cd apps/voice-agent/src` → `uv run pyinstaller server_main.spec`. El
  `.spec` versionado vive en `apps/voice-agent/src/server_main.spec` (junto al entry point, que
  es donde PyInstaller lo genera por default en la corrida exploratoria de "The Assignment") y
  el resultado queda en `apps/voice-agent/src/dist/server_main/`. El cwd de la invocación real
  de PyInstaller es `apps/voice-agent/src` — el mismo supuesto que ya usa `dev-up.ps1` y que
  Dependencies exige para los imports planos del proyecto.
- CI/CD (GitHub Actions) queda fuera de este plan salvo pedido explícito — se documenta como
  siguiente paso natural una vez el build local esté verificado.
- **Rollback:** Approach B (onedir) se distribuye como carpeta — el rollback más barato es
  conservar la carpeta `dist/server_main/` anterior antes de sobreescribir con un build nuevo
  (renombrarla, no borrarla, hasta confirmar que el build nuevo funciona). Mismo paso que el
  procedimiento de preservación de `sessions.db`/`video_storage`/cert de Open Questions — se
  ejecutan juntos en el mismo redeploy.
- **Scrub antes de distribuir — paso crítico, hallazgo de Eng review.** El smoke test offline de
  Success Criteria corre el `.exe` localmente, lo cual genera `server.crt`/`server.key`
  (autofirmado, idempotente — Premisa 6) y puede generar `sessions.db` en esa misma carpeta
  `dist/server_main/`. Si esa carpeta se zippea tal cual para TODOS los concesionarios, cada uno
  terminaría compartiendo la MISMA clave privada TLS — un antipatrón real incluso para TLS
  autofirmado solo-LAN. `build_exe.ps1` (o el runbook de distribución) debe borrar
  `server.crt`/`server.key`/`sessions.db`/`.env` de `dist/server_main/` inmediatamente antes de
  zippear para distribución — verificar/smoke-testear nunca debe contaminar el artefacto que
  efectivamente se envía.

## Dependencies

- `pyinstaller` no es dependencia del proyecto hoy (no aparece en `pyproject.toml`) — se agrega
  como dev-dependency (`uv add --dev pyinstaller`) para que el build sea reproducible desde
  `uv.lock`, en vez de asumir una instalación global fuera del venv gestionado.
- Requiere verificar que `faster-whisper`/`ctranslate2`, `kokoro`/`torch`/`transformers`, y
  `av`/PyAV tengan hooks de PyInstaller compatibles con las versiones fijadas en `uv.lock`
  (`faster-whisper>=1.2.1`, `kokoro>=0.9.4`) — se valida durante el build, no se asume de
  antemano (ver Claimed Limitations Need Evidence).
- Los imports del proyecto son planos (`audio`, `auth`, `core`, `server`, etc., sin prefijo
  `src.`) — hoy funcionan porque `dev-up.ps1` fija `-WorkingDirectory` a `src` y `pytest.ini`
  fija `pythonpath = src`. PyInstaller normalmente resuelve esto solo (agrega el directorio del
  script de entrada a su `sys.path` de análisis), pero el `.spec` debe invocarse desde
  `apps/voice-agent/src` para que coincida con ese mismo supuesto y evitar un build que "funciona
  desde ahí pero no desde la raíz del repo".

## The Assignment

Antes de tocar código: correr, desde `apps/voice-agent/src`, `uv run pyinstaller --collect-all
faster_whisper --collect-all ctranslate2 --collect-all onnxruntime --collect-all kokoro
--collect-all torch --collect-all transformers --collect-all av --collect-all sounddevice
--collect-all soundfile --collect-all uvicorn --onedir server_main.py` una vez, tal cual, sin
ningún hook custom todavía — la lista completa coincide con Premisa 5. El primer error de import
faltante que tire ese build es la lista real de gaps a cerrar — más confiable que adivinar hooks
de antemano, pero es un piso, no un techo: `ctranslate2`/`onnxruntime` pueden fallar en runtime de
inferencia sin tirar un import error, así que el smoke test de Success Criteria (STT/TTS real) es
lo que confirma que estos dos realmente quedaron bien empaquetados. Ese mismo build exploratorio
se corre copiando la carpeta `dist/server_main/` resultante a una máquina Windows limpia (no la de
desarrollo) y ejecutando el `.exe` ahí — es el paso que revela el comportamiento real de
SmartScreen contra un binario sin firmar (ver Open Questions). Ese hallazgo (hidden-imports/hooks
necesarios) se registra como comentarios directamente en el `.spec` versionado del repo, no en
un documento aparte — el `.spec` es la fuente de verdad del build de ahí en adelante.

**Ya corrido de verdad (no solo planeado) — 3 hallazgos reales, ninguno adivinado de antemano:**
1. `WinError 206` ("filename or extension is too long") en el paso `COLLECT`: los textos de
   licencia de `torch-*.dist-info/licenses/third_party/kineto/.../DCGM/...` están tan anidados
   que revientan el límite de 260 caracteres de Windows en cuanto el repo vive bajo una ruta
   moderadamente larga (ej. sincronizada con OneDrive). Fix aplicado en `server_main.spec`:
   filtrar `a.datas` (después de `Analysis()`, no antes — los hooks propios de PyInstaller
   vuelven a agregar esos datos de forma independiente) para excluir `*/dist-info/licenses/*`.
2. `language_tags` (dependencia transitiva de `kokoro` → `misaki` → `phonemizer` → `segments` →
   `csvw` → `language_tags`) trae un archivo de datos propio (`data/json/index.json`) que
   `--collect-all kokoro` no arrastra — `collect_all` de un paquete no recolecta los datos de SUS
   dependencias transitivas. No aparece como error de import en el build, solo al arrancar el
   `.exe` de verdad. Agregado a la lista de `--collect-all`.
3. `espeakng_loader` (dependencia de `misaki.espeak`, la fonemización de fallback de Kokoro) trae
   su propio directorio `espeak-ng-data` empaquetado, mismo patrón que (2). **Esto resuelve la
   Open Question de espeak-ng de abajo**: no hace falta instalar un binario nativo `espeak-ng`
   por separado en la máquina destino — `espeakng_loader` ya es una dependencia de pip que trae
   los datos necesarios, alcanza con `--collect-all espeakng_loader`.

Con los tres fixes aplicados, el `.exe` compilado arrancó de verdad en esta máquina (sin destino
limpio todavía — eso sigue pendiente) y: cargó torch/kokoro/faster-whisper/ctranslate2/
onnxruntime/sounddevice/soundfile sin errores de import, resolvió `base_dir()` correctamente al
directorio del propio `.exe` (confirmado por el mensaje de error mostrando la ruta correcta),
falló con el mensaje claro de Premisa 7 cuando faltaban los secretos requeridos (exit code 1,
confirmado), y con un `.env` de prueba + modelos placeholder, `_require_paths` encontró
correctamente los archivos vía `bundle_dir()` y se los pasó a `WhisperModel`/`KModel` (que
rechazaron el contenido placeholder con un error de CTranslate2 sobre versión de binario — la
ruta se resolvió bien, el contenido fake no). Falta correr `scripts/fetch_models.py` con pesos
reales y repetir el smoke test STT/TTS de Success Criteria en una máquina limpia — eso sigue sin
hacerse.

## What I noticed about how you think

- Pediste explícitamente "agregar las dependencias y requerimientos en el ejecutable" — ya
  tenías claro que el problema no es solo compilar, es el bundling completo. Eso es exactamente
  el punto donde la mayoría de los intentos de empaquetado con PyInstaller fallan a medias.
