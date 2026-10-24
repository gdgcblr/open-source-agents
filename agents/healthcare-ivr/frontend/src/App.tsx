import { Navigate, Route, Routes } from 'react-router'

import { Layout } from './components/Layout'
import { AppointmentsPage } from './pages/AppointmentsPage'
import { CallDetailPage } from './pages/CallDetailPage'
import { CallsPage } from './pages/CallsPage'
import { HospitalPage } from './pages/HospitalPage'
import { NotFoundPage } from './pages/NotFoundPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route index element={<Navigate to="/calls" replace />} />
        <Route path="calls" element={<CallsPage />} />
        <Route path="calls/:callId" element={<CallDetailPage />} />
        <Route path="appointments" element={<AppointmentsPage />} />
        <Route path="hospital" element={<HospitalPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  )
}
