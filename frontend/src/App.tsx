import { Navigate, Route, Routes } from 'react-router-dom'
import { HomeRedirect, RequireRole } from './auth/RequireRole'
import { Layout } from './components/Layout'
import { AcceptInvitation } from './pages/AcceptInvitation'
import { AdminAssignments, AdminUsers } from './pages/admin/Admin'
import { AfterSession } from './pages/client/AfterSession'
import { Appointments } from './pages/client/Appointments'
import { Entries } from './pages/client/Entries'
import { Moment } from './pages/client/Moment'
import { Plan } from './pages/client/Plan'
import { Summaries } from './pages/client/Summaries'
import { SummaryDetail } from './pages/client/SummaryDetail'
import { ClinicianClients, ClinicianSummaries, ClinicianSummaryDetail } from './pages/clinician/Clinician'
import { ClinicianClientDetail } from './pages/clinician/ClientDetail'
import { Login } from './pages/Login'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/accept-invitation" element={<AcceptInvitation />} />
      <Route element={<RequireRole role="client" />}>
        <Route element={<Layout />}>
          <Route path="/client" element={<Navigate to="/client/entries" replace />} />
          <Route path="/client/entries" element={<Entries />} />
          <Route path="/client/summaries" element={<Summaries />} />
          <Route path="/client/summaries/:id" element={<SummaryDetail />} />
          <Route path="/client/after-session" element={<AfterSession />} />
          <Route path="/client/appointments" element={<Appointments />} />
          <Route path="/client/plan" element={<Plan />} />
          <Route path="/client/moment" element={<Moment />} />
        </Route>
      </Route>
      <Route element={<RequireRole role="clinician" />}>
        <Route element={<Layout />}>
          <Route path="/clinician" element={<Navigate to="/clinician/clients" replace />} />
          <Route path="/clinician/clients" element={<ClinicianClients />} />
          <Route path="/clinician/clients/:id" element={<ClinicianClientDetail />} />
          <Route path="/clinician/summaries" element={<ClinicianSummaries />} />
          <Route path="/clinician/summaries/:id" element={<ClinicianSummaryDetail />} />
        </Route>
      </Route>
      <Route element={<RequireRole role="org_admin" />}>
        <Route element={<Layout />}>
          <Route path="/admin" element={<Navigate to="/admin/users" replace />} />
          <Route path="/admin/users" element={<AdminUsers />} />
          <Route path="/admin/assignments" element={<AdminAssignments />} />
        </Route>
      </Route>
      <Route path="*" element={<HomeRedirect />} />
    </Routes>
  )
}
