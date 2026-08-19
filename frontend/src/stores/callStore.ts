import { create } from 'zustand'

type CallState = {
  status: 'idle' | 'connecting' | 'connected' | 'completed'
  seconds: number
  paused: boolean
  dispatcherSpeaking: boolean
  setStatus: (status: CallState['status']) => void
  tick: () => void
  togglePause: () => void
  setDispatcherSpeaking: (value: boolean) => void
  reset: () => void
}

export const useCallStore = create<CallState>((set) => ({
  status: 'idle',
  seconds: 0,
  paused: false,
  dispatcherSpeaking: true,
  setStatus: (status) => set({ status }),
  tick: () => set((state) => state.paused ? state : { seconds: state.seconds + 1 }),
  togglePause: () => set((state) => ({ paused: !state.paused })),
  setDispatcherSpeaking: (dispatcherSpeaking) => set({ dispatcherSpeaking }),
  reset: () => set({ status: 'idle', seconds: 0, paused: false, dispatcherSpeaking: true }),
}))
