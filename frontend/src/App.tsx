import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import CallPage from './pages/CallPage'
import ReviewPage from './pages/ReviewPage'
import PerformancePage from './pages/PerformancePage'
import ScenariosPage from './pages/ScenariosPage'
import ScenarioEditorPage from './pages/ScenarioEditorPage'
import ResourcesPage from './pages/ResourcesPage'
import SettingsPage from './pages/SettingsPage'
import LoginPage from './pages/LoginPage'
import { useEngineStore } from './stores/engineStore'

export default function App() {
  const initialize = useEngineStore((state) => state.initialize)
  const authToken = useEngineStore((state) => state.authToken)
  useEffect(() => initialize(), [initialize])

  // Fase 2 (cierre del gap de Fase 1): sin token de sesión (ADR-0008/NFR-04) el WS real rechaza
  // toda conexión — no tiene sentido mostrar ninguna pantalla que dependa del engine todavía.
  if (!authToken) return <LoginPage />

  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/call" element={<CallPage />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/performance" element={<PerformancePage />} />
      <Route path="/training" element={<Navigate to="/" replace />} />
      <Route path="/scenarios" element={<ScenariosPage />} />
      <Route path="/scenarios/new" element={<ScenarioEditorPage />} />
      <Route path="/scenarios/:scenarioId/edit" element={<ScenarioEditorPage />} />
      <Route path="/resources" element={<ResourcesPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
