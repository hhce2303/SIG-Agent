<#
.SYNOPSIS
    Construye un único instalador Windows con el cliente Electron y el backend PyInstaller.

.DESCRIPTION
    El backend se compila y limpia primero. Electron-builder lo incluye completo bajo
    resources/backend y produce el instalador NSIS. Ningún `.env`, certificado ni base de datos
    entra al instalador.

.PARAMETER RefetchModels
    Fuerza volver a descargar los modelos antes de construir el backend.

.PARAMETER SkipBackend
    Reutiliza el backend ya construido. Solo para iterar sobre Electron/NSIS después de que el
    backend actual haya sido compilado y validado al menos una vez.
#>

param(
    [switch]$RefetchModels,
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"
$RepoRoot = $PSScriptRoot
$FrontendDir = Join-Path $RepoRoot 'frontend'
$BackendBuildScript = Join-Path $RepoRoot 'build_exe.ps1'
$BackendExe = Join-Path $RepoRoot 'apps\voice-agent\src\dist\server_main\server_main.exe'
$FrontendPackage = Get-Content -Raw (Join-Path $FrontendDir 'package.json') | ConvertFrom-Json
$InstallerName = "$($FrontendPackage.build.productName) Setup $($FrontendPackage.version).exe"
$InstallerPath = Join-Path $FrontendDir "release\$InstallerName"
$InstallerHashPath = "$InstallerPath.sha256"

Write-Host "=== 1/3: backend PyInstaller ===" -ForegroundColor Cyan
if ($SkipBackend) {
    Write-Host "REUTILIZADO (-SkipBackend): $BackendExe" -ForegroundColor Yellow
} else {
    $backendArguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $BackendBuildScript, '-SkipArchive')
    if ($RefetchModels) { $backendArguments += '-RefetchModels' }
    & powershell.exe @backendArguments
    if ($LASTEXITCODE -ne 0) { throw "El build del backend fallo (codigo $LASTEXITCODE)." }
}
if (-not (Test-Path -LiteralPath $BackendExe -PathType Leaf)) {
    throw "No se encontro el backend esperado: $BackendExe"
}

Write-Host "=== 2/3: instalador Electron + backend ===" -ForegroundColor Cyan
Push-Location $FrontendDir
try {
    & npm.cmd run dist:win
    if ($LASTEXITCODE -ne 0) { throw "electron-builder fallo (codigo $LASTEXITCODE)." }
} finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) {
    throw "El build termino pero no se encontro: $InstallerPath"
}

Write-Host "=== 3/3: checksum ===" -ForegroundColor Cyan
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash
[System.IO.File]::WriteAllText($InstallerHashPath, "$hash  $(Split-Path $InstallerPath -Leaf)`r`n")

Write-Host "Instalador: $InstallerPath" -ForegroundColor Green
Write-Host "SHA-256: $hash"
