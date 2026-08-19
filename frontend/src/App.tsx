import { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import HomePage from './pages/HomePage'
import CallPage from './pages/CallPage'
import ReviewPage from './pages/ReviewPage'
import PerformancePage from './pages/PerformancePage'
import ScenariosPage from './pages/ScenariosPage'
import ResourcesPage from './pages/ResourcesPage'
import SettingsPage from './pages/SettingsPage'
import { useEngineStore } from './stores/engineStore'

export default function App() {
  const initialize = useEngineStore((state) => state.initialize)
  useEffect(() => initialize(), [initialize])
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/call" element={<CallPage />} />
      <Route path="/review" element={<ReviewPage />} />
      <Route path="/performance" element={<PerformancePage />} />
      <Route path="/training" element={<Navigate to="/" replace />} />
      <Route path="/scenarios" element={<ScenariosPage />} />
      <Route path="/resources" element={<ResourcesPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
