const { spawn } = require('child_process')
const fs = require('fs')
const https = require('https')
const path = require('path')
const { app, dialog, shell } = require('electron')

const REQUIRED_ENV_KEYS = [
  'ANTHROPIC_API_KEY',
  'CLAUDE_MODEL',
  'SESSION_TOKEN_SECRET',
  'SUPERVISOR_PASSPHRASE',
]
const HEALTH_URL = 'https://127.0.0.1:8000/health'
const STARTUP_TIMEOUT_MS = 120_000
const HEALTH_RETRY_MS = 750

let backendProcess = null

function backendDataDir() {
  const localAppData = process.env.LOCALAPPDATA
  if (localAppData) return path.join(localAppData, 'SIG Agent', 'data')
  return path.join(app.getPath('userData'), 'backend-data')
}

function backendBundleDir() {
  return path.join(process.resourcesPath, 'backend')
}

function parseConfiguredKeys(contents) {
  const configured = new Set()
  for (const rawLine of contents.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const separator = line.indexOf('=')
    if (separator < 1) continue
    const key = line.slice(0, separator).trim()
    const value = line.slice(separator + 1).trim().replace(/^(['"])(.*)\1$/, '$2')
    if (value) configured.add(key)
  }
  return configured
}

async function ensureConfiguration() {
  const dataDir = backendDataDir()
  const envPath = path.join(dataDir, '.env')
  const templatePath = path.join(backendBundleDir(), '.env.example')
  fs.mkdirSync(dataDir, { recursive: true })

  if (!fs.existsSync(envPath)) {
    if (!fs.existsSync(templatePath)) {
      throw new Error(`No se encontró la plantilla de configuración: ${templatePath}`)
    }
    fs.copyFileSync(templatePath, envPath, fs.constants.COPYFILE_EXCL)
  }

  const configuredKeys = parseConfiguredKeys(fs.readFileSync(envPath, 'utf8'))
  const missing = REQUIRED_ENV_KEYS.filter((key) => !configuredKeys.has(key))
  if (missing.length === 0) return { dataDir, envPath }

  await dialog.showMessageBox({
    type: 'info',
    title: 'Configurar SIG Agent',
    message: 'Falta completar la configuración del backend.',
    detail: `Complete estas variables en el archivo que se abrirá:\n\n${missing.join(', ')}\n\nDespués guarde el archivo y vuelva a abrir SIG Agent.`,
    buttons: ['Abrir configuración'],
    defaultId: 0,
  })
  await shell.openPath(envPath)
  return null
}

function healthCheck() {
  return new Promise((resolve) => {
    const request = https.get(HEALTH_URL, { rejectUnauthorized: false, timeout: 2_000 }, (response) => {
      response.resume()
      resolve(response.statusCode === 200)
    })
    request.on('timeout', () => {
      request.destroy()
      resolve(false)
    })
    request.on('error', () => resolve(false))
  })
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

async function waitUntilHealthy(child) {
  const deadline = Date.now() + STARTUP_TIMEOUT_MS
  while (Date.now() < deadline) {
    if (await healthCheck()) return
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`El backend terminó antes de estar listo (código ${child.exitCode ?? 'desconocido'}).`)
    }
    await delay(HEALTH_RETRY_MS)
  }
  throw new Error(`El backend no respondió en ${STARTUP_TIMEOUT_MS / 1000} segundos.`)
}

async function startBackend() {
  if (!app.isPackaged) return true

  const configuration = await ensureConfiguration()
  if (!configuration) return false

  // Si otra instancia compatible ya escucha, no se crea un segundo backend ni se reclama su
  // ciclo de vida. El single-instance lock de Electron cubre el caso normal; este chequeo
  // también cubre un backend iniciado manualmente para soporte.
  if (await healthCheck()) return true

  const executablePath = path.join(backendBundleDir(), 'server_main.exe')
  if (!fs.existsSync(executablePath)) {
    throw new Error(`No se encontró el backend empaquetado: ${executablePath}`)
  }

  backendProcess = spawn(executablePath, [], {
    cwd: configuration.dataDir,
    env: {
      ...process.env,
      SIG_AGENT_DATA_DIR: configuration.dataDir,
    },
    // PyInstaller fue construido con console=True. En esta primera entrega la consola queda
    // visible para diagnóstico en campo; una versión posterior puede ocultarla porque también
    // existe logs/server.log.
    windowsHide: false,
    detached: true,
    stdio: 'ignore',
  })

  backendProcess.on('error', (error) => console.error('[backend] process error', error))
  backendProcess.on('exit', (code, signal) => {
    console.log('[backend] process exited', { code, signal })
    backendProcess = null
  })

  await waitUntilHealthy(backendProcess)
  return true
}

async function stopBackend() {
  const child = backendProcess
  if (!child || child.exitCode !== null) return

  child.kill('SIGTERM')
  const stopped = await Promise.race([
    new Promise((resolve) => child.once('exit', () => resolve(true))),
    delay(5_000).then(() => false),
  ])
  if (!stopped && child.exitCode === null) child.kill('SIGKILL')
  backendProcess = null
}

module.exports = {
  backendDataDir,
  parseConfiguredKeys,
  startBackend,
  stopBackend,
}
