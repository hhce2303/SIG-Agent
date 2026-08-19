const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('sigDesktop', {
  platform: process.platform,
  version: '0.1.0',
})
