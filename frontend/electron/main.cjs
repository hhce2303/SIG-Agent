const { app, BrowserWindow } = require('electron')
const { autoUpdater } = require('electron-updater')
const path = require('path')

// Fase 3 (roadmap): "auto-update del cliente Electron" — sin esto, actualizar cada PC de
// supervisor requiere ir máquina por máquina en persona. `electron-builder`'s `publish` config
// (`package.json`) apunta a GitHub Releases del repo real (público, sin token necesario para
// leer) — quien corta un release corre `npm run release:win` (requiere `GH_TOKEN` con permiso
// de subir assets, solo en la máquina que empaqueta, nunca en el cliente).
//
// `checkForUpdatesAndNotify` usa la notificación nativa del SO cuando ya se descargó una
// actualización (se aplica al reiniciar la app) — no se construyó un diálogo custom para esto,
// sería una segunda UI para lo mismo que el SO ya resuelve. Solo corre empaquetado
// (`app.isPackaged`): en desarrollo (`npm run dev`) no hay artefacto firmado que actualizar, y
// además fallaría contra el dev server.
const UPDATE_CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // cada 4h — la app corre todo el turno.

function initAutoUpdate() {
  if (!app.isPackaged) return

  autoUpdater.logger = console
  autoUpdater.on('error', (error) => console.error('[auto-update] error', error))
  autoUpdater.on('update-available', (info) => console.log('[auto-update] update available', info.version))
  autoUpdater.on('update-not-available', () => console.log('[auto-update] already up to date'))
  autoUpdater.on('update-downloaded', (info) => console.log('[auto-update] downloaded, will install on quit', info.version))

  autoUpdater.checkForUpdatesAndNotify()
  setInterval(() => autoUpdater.checkForUpdatesAndNotify(), UPDATE_CHECK_INTERVAL_MS)
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1491,
    height: 1055,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: '#061321',
    title: 'SIG Agent',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })

  const devServer = process.env.VITE_DEV_SERVER_URL
  if (devServer) {
    win.loadURL(devServer)
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'))
  }
}

// Fase 2 (cierre del gap de Fase 1): el servidor real corre WSS/TLS con un certificado
// autofirmado por defecto (NFR-05, `server/tls.py`) — sin esto, Electron rechaza tanto la
// conexión WebSocket como el login por REST contra ese certificado, y el login nunca funciona
// contra el backend real. Esto confía en CUALQUIER certificado inválido para toda la app, lo
// cual es aceptable para el modelo de despliegue actual (LAN interna de un solo concesionario,
// ADR-0004) pero es una concesión de seguridad real, no cosmética — el endurecimiento correcto
// es fijar (pin) el fingerprint del certificado específico del servidor configurado en vez de
// aceptar cualquiera; queda pendiente como mejora, no como parte de este alcance.
app.on('certificate-error', (event, _webContents, _url, _error, _certificate, callback) => {
  event.preventDefault()
  callback(true)
})

app.whenReady().then(() => {
  createWindow()
  initAutoUpdate()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
