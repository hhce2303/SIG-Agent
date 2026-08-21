<#
.SYNOPSIS
    Levanta el backend real (Whisper + Claude + Kokoro + mic, sin stubs) y el frontend Electron
    real para pruebas manuales a través del scope de la UI real.

.DESCRIPTION
    No reemplaza los tests automatizados (`pytest` en apps/voice-agent, `npm run build` en
    frontend) - es el equivalente a "dos terminales abiertas" que ya documenta el README, pero
    con el orden de arranque, el chequeo de salud, y las variables de entorno correctas
    resueltos una sola vez en vez de repetidos a mano en cada sesión.

    Los dos procesos corren de fondo (sin ventana de consola propia) y su salida va a archivos
    de log bajo .dev-up-tmp/ - la primera versión de este script abría una ventana de PowerShell
    nueva por proceso, pero eso depende de que el terminal (Windows Terminal, VS Code, etc.)
    efectivamente cree una ventana visible, y en la práctica no fue confiable. Los procesos en
    sí son reales e independientes (sobreviven aunque cierres la terminal que corrió este
    script) - lo único que cambió es cómo se ve su output.

    Por default corre con WSS/TLS real (NFR-05, ver docs/architecture/nfr.md) - el cliente
    Electron ya confía en el certificado autofirmado (`certificate-error` en
    frontend/electron/main.cjs), así que esto valida la postura de seguridad real, no un atajo.
    Usa -DisableTls solo para debug rápido en texto plano (mismo escape hatch que ya documenta
    server_main.py, nunca para nada que no sea esta máquina).

.PARAMETER DisableTls
    Corre el backend sin WSS/TLS (DISABLE_TLS=1) - solo desarrollo local.

.PARAMETER Stop
    Detiene el backend y el frontend que este script haya levantado (por puerto), sin levantar
    nada nuevo.

.PARAMETER Logs
    En vez de levantar nada, muestra las últimas líneas de los logs de backend/frontend y los
    sigue en vivo (como `tail -f`). Ctrl+C para salir de esto sin detener los procesos.

.EXAMPLE
    ./dev-up.ps1
.EXAMPLE
    ./dev-up.ps1 -DisableTls
.EXAMPLE
    ./dev-up.ps1 -Logs
.EXAMPLE
    ./dev-up.ps1 -Stop
#>

param(
    [switch]$DisableTls,
    [switch]$Stop,
    [switch]$Logs
)

$RepoRoot = $PSScriptRoot
$BackendSrc = Join-Path $RepoRoot 'apps\voice-agent\src'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
$EnvFile = Join-Path $RepoRoot '.env'
$FrontendEnvFile = Join-Path $FrontendDir '.env'
$TmpDir = Join-Path $RepoRoot '.dev-up-tmp'
$BackendLog = Join-Path $TmpDir 'backend.log'
$FrontendLog = Join-Path $TmpDir 'frontend.log'
$PidFile = Join-Path $TmpDir 'pids.json'

function Stop-ByPort([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Detenido proceso en puerto $Port (PID $($c.OwningProcess))."
    }
    if (-not $conns) {
        Write-Host "Nada escuchando en el puerto $Port."
    }
}

if ($Stop) {
    if (Test-Path $PidFile) {
        $pids = Get-Content $PidFile -Raw | ConvertFrom-Json
        foreach ($p in @($pids.backend, $pids.frontend)) {
            if ($p) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }
        }
        Remove-Item $PidFile -ErrorAction SilentlyContinue
    }
    # Por puerto también, en caso de que el pid file esté desactualizado (ej. npm relanzó hijos).
    Stop-ByPort 8000
    Stop-ByPort 5180
    exit 0
}

if ($Logs) {
    if (-not (Test-Path $BackendLog) -and -not (Test-Path $FrontendLog)) {
        Write-Error "No hay logs todavía en $TmpDir - corre ./dev-up.ps1 primero."
    }
    Write-Host "--- backend.log / frontend.log (Ctrl+C para salir, no detiene nada) ---" -ForegroundColor Cyan
    Get-Content -Path $BackendLog, $FrontendLog -Tail 20 -Wait -ErrorAction SilentlyContinue
    exit 0
}

# --- Validaciones previas -------------------------------------------------

if (-not (Test-Path $VenvPython)) {
    Write-Error "No se encontró el venv en $VenvPython. Corre 'uv sync' (o el equivalente) primero."
    exit 1
}
if (-not (Test-Path (Join-Path $FrontendDir 'node_modules'))) {
    Write-Error "Falta frontend/node_modules. Corre 'npm install' dentro de frontend/ primero."
    exit 1
}
if (-not (Test-Path $EnvFile)) {
    Write-Error "No existe $EnvFile. Ver docs/architecture/adr/0008-mecanismo-de-autenticacion-de-sesion.md para las claves que necesita."
    exit 1
}

$envContent = Get-Content $EnvFile -Raw
$requiredKeys = 'ANTHROPIC_API_KEY', 'CLAUDE_MODEL', 'SESSION_TOKEN_SECRET', 'SUPERVISOR_PASSPHRASE'
$missing = $requiredKeys | Where-Object { $envContent -notmatch "(?m)^$_=" }
if ($missing) {
    Write-Error "Faltan estas claves en .env: $($missing -join ', ')"
    exit 1
}

New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
Remove-Item $BackendLog, $FrontendLog -ErrorAction SilentlyContinue

# --- Config de TLS y frontend ---------------------------------------------

if ($DisableTls) {
    $wsScheme = 'ws'
    $healthScheme = 'http'
    $env:DISABLE_TLS = '1'
    Write-Host "TLS deshabilitado (-DisableTls) - solo para debug local, viola NFR-05." -ForegroundColor Yellow
} else {
    $wsScheme = 'wss'
    $healthScheme = 'https'
    Remove-Item Env:\DISABLE_TLS -ErrorAction SilentlyContinue
    Write-Host "TLS real activado (default) - certificado autofirmado, el cliente Electron ya confía en él."
}

Set-Content -Path $FrontendEnvFile -Value "VITE_BACKEND_WS_URL=${wsScheme}://127.0.0.1:8000"
Write-Host "frontend/.env -> VITE_BACKEND_WS_URL=${wsScheme}://127.0.0.1:8000"

# --- Backend (proceso real, sin ventana propia, log a archivo) ------------

Write-Host "Arrancando backend real (Whisper + Claude + Kokoro + mic)..."
$backendProc = Start-Process -FilePath $VenvPython -ArgumentList 'server_main.py' `
    -WorkingDirectory $BackendSrc -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $BackendLog -RedirectStandardError "$BackendLog.err"

# server_main.py escribe la mayoría de sus logs por stderr (default de logging de Python) -
# se combinan ambos en el mismo archivo visible para -Logs, en el orden en que Windows los vaya
# volcando (no intercalados por timestamp real, son dos streams separados).
Get-Content "$BackendLog.err" -ErrorAction SilentlyContinue | Add-Content -Path $BackendLog -ErrorAction SilentlyContinue

# --- Espera activa a que el backend responda -------------------------------

$healthUrl = "${healthScheme}://127.0.0.1:8000/health"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 2
    if ($backendProc.HasExited) {
        Write-Error "El proceso del backend murió (código $($backendProc.ExitCode)) - revisa $BackendLog y $BackendLog.err"
        exit 1
    }
    $result = & curl.exe -sk -o NUL -w "%{http_code}" $healthUrl 2>$null
    if ($result -eq '200') { $ready = $true; break }
    Write-Host "Esperando al backend... ($($i + 1)/60)"
}

if (-not $ready) {
    Write-Warning "El backend no respondió en /health tras ~2 minutos. Revisa $BackendLog y $BackendLog.err (la descarga de modelos la primera vez puede tardar más)."
    Write-Host "Últimas líneas de $BackendLog.err:" -ForegroundColor Yellow
    Get-Content "$BackendLog.err" -Tail 15 -ErrorAction SilentlyContinue
} else {
    Write-Host "Backend listo en $healthUrl (PID $($backendProc.Id))" -ForegroundColor Green
}

# --- Frontend (Electron real, ventana propia de Electron sí es visible) ---

# Si esta terminal corre dentro de VS Code (o cualquier host basado en Electron), a veces hereda
# ELECTRON_RUN_AS_NODE=1 - eso fuerza a `electron .` a correr como Node.js plano en vez de la
# app real (`require('electron').app` queda `undefined`), y `electron-updater` crashea al
# arrancar tratando de leer la versión de una app que no existe. No es un bug de
# `frontend/electron/main.cjs` - es incompatible con este modo degradado por diseño. Se limpia
# acá, no se asume que el proceso padre nunca la tuvo seteada.
Remove-Item Env:\ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue

Write-Host "Arrancando frontend (Vite + Electron)..."
$frontendProc = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm run dev' `
    -WorkingDirectory $FrontendDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $FrontendLog -RedirectStandardError "$FrontendLog.err"

@{ backend = $backendProc.Id; frontend = $frontendProc.Id } | ConvertTo-Json | Set-Content $PidFile

Write-Host ""
Write-Host "=== Listo ===" -ForegroundColor Cyan
Write-Host "Backend:  $healthUrl (PID $($backendProc.Id))"
Write-Host "Frontend: PID $($frontendProc.Id) - la ventana de la app Electron debería abrir sola en 5-15s."
Write-Host "Passphrase de supervisor: la que está en SUPERVISOR_PASSPHRASE dentro de .env (raíz del repo)."
Write-Host "Supervisor name: cualquiera - se guarda tal cual lo escribas."
Write-Host ""
Write-Host "Si el login da 'Failed to fetch': el campo 'Backend URL' en 'Advanced' de la pantalla" -ForegroundColor Yellow
Write-Host "de login se guarda en localStorage y tiene prioridad sobre el .env - si quedó un valor" -ForegroundColor Yellow
Write-Host "viejo de una sesión anterior, ponlo en manualmente $wsScheme`://127.0.0.1:8000 y da Sign in de nuevo." -ForegroundColor Yellow
Write-Host ""
Write-Host "Ver logs en vivo:  ./dev-up.ps1 -Logs"
Write-Host "Detener todo:      ./dev-up.ps1 -Stop"
