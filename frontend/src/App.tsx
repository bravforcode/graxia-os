import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import Dashboard from './pages/Dashboard'
import Opportunities from './pages/Opportunities'
import Drafts from './pages/Drafts'
import Contacts from './pages/Contacts'
import Metrics from './pages/Metrics'
import Jobs from './pages/Jobs'
import EmailThreads from './pages/EmailThreads'
import Tasks from './pages/Tasks'
import Costs from './pages/Costs'
import EventBus from './pages/EventBus'
import Settings from './pages/Settings'
import Login from './pages/Login'
import Register from './pages/Register'
import Layout from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'

export function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      
      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="opportunities" element={<Opportunities />} />
        <Route path="drafts" element={<Drafts />} />
        <Route path="contacts" element={<Contacts />} />
        <Route path="metrics" element={<Metrics />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="emails" element={<EmailThreads />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="costs" element={<Costs />} />
        <Route path="event-bus" element={<EventBus />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
