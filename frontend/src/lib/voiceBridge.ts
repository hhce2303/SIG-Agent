import type { EngineCommand, EngineEvent } from '../types'
import { DEFAULT_BACKEND_WS_URL } from '../config'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected'

class VoiceBridge {
  private socket?: WebSocket
  private url = DEFAULT_BACKEND_WS_URL
  private listeners = new Set<(event: EngineEvent) => void>()
  private statusListeners = new Set<(status: ConnectionStatus) => void>()
  private queue: string[] = []
  private reconnectTimer?: number
  private intentionallyClosed = false

  connect(url = this.url) {
    this.url = url
    this.intentionallyClosed = false
    if (this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) return
    this.publishStatus('connecting')
    this.socket = new WebSocket(url)
    this.socket.onopen = () => {
      this.publishStatus('connected')
      this.queue.splice(0).forEach((message) => this.socket?.send(message))
    }
    this.socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as EngineEvent
        this.listeners.forEach((listener) => listener(event))
      } catch {
        this.listeners.forEach((listener) => listener({ event: 'error', message: 'Received an invalid engine response.', recoverable: true }))
      }
    }
    this.socket.onerror = () => this.publishStatus('disconnected')
    this.socket.onclose = () => {
      this.publishStatus('disconnected')
      if (!this.intentionallyClosed) {
        window.clearTimeout(this.reconnectTimer)
        this.reconnectTimer = window.setTimeout(() => this.connect(), 2000)
      }
    }
  }

  reconnect(url: string) {
    this.intentionallyClosed = true
    this.socket?.close()
    this.socket = undefined
    window.clearTimeout(this.reconnectTimer)
    this.url = url
    window.setTimeout(() => this.connect(url), 0)
  }

  // Fase 2 (login): a diferencia de `reconnect`, esto no vuelve a abrir nada — se usa al cerrar
  // sesión o cuando cambia el backend configurado y hace falta un login nuevo antes de conectar.
  disconnect() {
    this.intentionallyClosed = true
    window.clearTimeout(this.reconnectTimer)
    this.socket?.close()
    this.socket = undefined
    this.queue = []
    this.publishStatus('disconnected')
  }

  subscribe(listener: (event: EngineEvent) => void) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  subscribeStatus(listener: (status: ConnectionStatus) => void) {
    this.statusListeners.add(listener)
    return () => this.statusListeners.delete(listener)
  }

  send(command: EngineCommand) {
    const message = JSON.stringify(command)
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(message)
    else this.queue.push(message)
  }

  private publishStatus(status: ConnectionStatus) {
    this.statusListeners.forEach((listener) => listener(status))
  }
}

export const voiceBridge = new VoiceBridge()
