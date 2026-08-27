<#
.SYNOPSIS
    Construye el ejecutable standalone del backend de voice-agent (PyInstaller --onedir) y lo
    deja listo para distribuir a la caja LAN de un concesionario.

.DESCRIPTION
    Ver docs/designs/empaquetado-ejecutable-backend.md para el diseño completo. Secuencia:
      1. `uv sync` (raíz del repo) — instala `pyinstaller` como dev-dependency.
      2. `scripts/fetch_models.py` — descarga los pesos de Whisper/Kokoro a `models/` (una vez,
         se salta si ya existen, salvo `-RefetchModels`).
      3. `pyinstaller server_main.spec` desde `apps/voice-agent/src` (mismo cwd que `dev-up.ps1`
         — los imports planos del proyecto dependen de eso).
      4. **Scrub antes de distribuir** (hallazgo de la revisión de ingeniería, Distribution
         Plan del design doc): borra `server.crt`/`server.key`/`sessions.db`/`.env` de
         `dist/server_main/` — el smoke test local genera esos archivos, y si la carpeta se
         zippea tal cual para TODOS los concesionarios, cada uno terminaría compartiendo la
         MISMA clave privada TLS.
      5. Rollback: si ya existe un build anterior en `dist/`, se renombra a `dist.previous/`
         antes de reemplazarlo — nunca se borra hasta confirmar que el build nuevo funciona.

.PARAMETER RefetchModels
    Fuerza volver a descargar los pesos de modelo aunque `models/` ya exista (ej. cambiaste
    `KOKORO_VOICE` o `WHISPER_MODEL_SIZE`).

.PARAMETER SkipScrub
    NO usar en un build real de distribución — salta el paso de scrub de secretos/estado. Solo
    para debug local cuando querés inspeccionar el `.env`/certificado generados por el smoke
    test.

.EXAMPLE
    ./build_exe.ps1
.EXAMPLE
    ./build_exe.ps1 -RefetchModels
#>

param(
    [switch]$RefetchModels,
    [switch]$SkipScrub
)

$ErrorActionPreference = "Stop"

$RepoRoot = $PSScriptRoot
$BackendSrc = Join-Path $RepoRoot 'apps\voice-agent\src'
$ModelsDir = Join-Path $RepoRoot 'models'
$DistDir = Join-Path $BackendSrc 'dist\server_main'
$PreviousDistDir = Join-Path $BackendSrc 'dist.previous\server_main'
$WhisperModelDir = Join-Path $ModelsDir 'whisper'
$KokoroModelDir = Join-Path $ModelsDir 'kokoro'
$KokoroVoice = if ($env:KOKORO_VOICE) { $env:KOKORO_VOICE } else { 'am_michael' }
$RequiredModelFiles = @(
    (Join-Path $WhisperModelDir 'model.bin'),
    (Join-Path $WhisperModelDir 'config.json'),
    (Join-Path $KokoroModelDir 'config.json'),
    (Join-Path $KokoroModelDir 'kokoro-v1_0.pth'),
    (Join-Path $KokoroModelDir "voices\$KokoroVoice.pt")
)

Write-Host "=== 1/4: uv sync (raiz del repo) ===" -ForegroundColor Cyan
Push-Location $RepoRoot
try {
    # --frozen hace que uv.lock sea la fuente de verdad. --inexact evita que el build falle
    # intentando borrar paquetes ajenos o bloqueados dentro de un .venv sincronizado por
    # OneDrive; las versiones requeridas por el lock se siguen instalando/verificando.
    uv sync --frozen --inexact
    if ($LASTEXITCODE -ne 0) { throw "uv sync fallo (codigo $LASTEXITCODE)" }
} finally {
    Pop-Location
}

Write-Host "=== 2/4: fetch_models.py ===" -ForegroundColor Cyan
$MissingModelFiles = @($RequiredModelFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if (($MissingModelFiles.Count -eq 0) -and -not $RefetchModels) {
    Write-Host "Los pesos requeridos ya existen; se salta la descarga (usa -RefetchModels para forzarla)."
} else {
    if ($MissingModelFiles.Count -gt 0) {
        Write-Host "Faltan $($MissingModelFiles.Count) archivos de modelo; se descargaran ahora."
    }
    Push-Location $RepoRoot
    try {
        uv run python scripts/fetch_models.py
        if ($LASTEXITCODE -ne 0) { throw "fetch_models.py fallo (codigo $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
}

$MissingModelFiles = @($RequiredModelFiles | Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
if ($MissingModelFiles.Count -gt 0) {
    throw "La descarga termino incompleta. Faltan: $($MissingModelFiles -join ', ')"
}

Write-Host "=== 3/4: pyinstaller server_main.spec ===" -ForegroundColor Cyan
# Rollback: preservar el build anterior ANTES de que pyinstaller lo sobreescriba — mismo paso
# que preservar sessions.db/video_storage/cert en un redeploy real (Open Questions del design
# doc), acá aplicado al propio build.
if (Test-Path $DistDir) {
    if (Test-Path $PreviousDistDir) { Remove-Item -Recurse -Force $PreviousDistDir }
    New-Item -ItemType Directory -Force -Path (Split-Path $PreviousDistDir) | Out-Null
    Move-Item $DistDir $PreviousDistDir
    Write-Host "Build anterior conservado en $PreviousDistDir (rollback: mover de vuelta a dist/server_main si el build nuevo falla)."
}

Push-Location $BackendSrc
try {
    uv run pyinstaller server_main.spec --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller fallo (codigo $LASTEXITCODE)" }
} finally {
    Pop-Location
}

if (-not (Test-Path (Join-Path $DistDir 'server_main.exe'))) {
    throw "El build termino pero no se encontro $DistDir\server_main.exe; revisar el log de pyinstaller arriba."
}

Write-Host "=== 4/4: scrub de secretos/estado antes de distribuir ===" -ForegroundColor Cyan
if ($SkipScrub) {
    Write-Host "SALTEADO (-SkipScrub): NO zippear esta carpeta para un concesionario real; contiene secretos/estado del smoke test local." -ForegroundColor Yellow
} else {
    $ScrubTargets = @('server.crt', 'server.key', 'sessions.db', '.env') | ForEach-Object {
        Join-Path $DistDir $_
    }
    foreach ($target in $ScrubTargets) {
        if (Test-Path $target) {
            Remove-Item -Force $target
            Write-Host "  borrado: $target"
        }
    }
    Write-Host "Scrub completo: $DistDir esta lista para zippear y distribuir." -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor Cyan
Write-Host "Ejecutable: $DistDir\server_main.exe"
Write-Host "Antes de distribuir a un concesionario NUEVO: copiar un .env real (con los secretos"
Write-Host "reales) a esa carpeta; el .env del smoke test fue borrado a proposito arriba."
Write-Host ""
Write-Host "Antes de REDISTRIBUIR una actualizacion a un concesionario EXISTENTE: preservar"
Write-Host "sessions.db / video_storage/ / server.crt / server.key / .env del despliegue actual"
Write-Host "ANTES de reemplazar su carpeta (ver Open Questions en"
Write-Host "docs/designs/empaquetado-ejecutable-backend.md); este script no lo hace por vos,"
Write-Host "porque no tiene acceso a la maquina del concesionario."
