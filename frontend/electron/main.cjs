const { app, BrowserWindow } = require('electron')
const path = require('path')

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
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})
