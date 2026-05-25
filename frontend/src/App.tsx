import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./contexts/AuthContext";

const UnifiedDashboard = lazy(() => import("./pages/UnifiedDashboard"));
const ApprovalQueue = lazy(() => import("./pages/ApprovalQueue"));
const Opportunities = lazy(() => import("./pages/Opportunities"));
const Drafts = lazy(() => import("./pages/Drafts"));
const Contacts = lazy(() => import("./pages/Contacts"));
const Leads = lazy(() => import("./pages/Leads"));
const Metrics = lazy(() => import("./pages/Metrics"));
const Jobs = lazy(() => import("./pages/Jobs"));
const EmailThreads = lazy(() => import("./pages/EmailThreads"));
const Tasks = lazy(() => import("./pages/Tasks"));
const Costs = lazy(() => import("./pages/Costs"));
const EventBus = lazy(() => import("./pages/EventBus"));
const Agents = lazy(() => import("./pages/Agents"));
const Settings = lazy(() => import("./pages/Settings"));
const Login = lazy(() => import("./pages/Login"));
const Register = lazy(() => import("./pages/Register"));
const NotFound = lazy(() => import("./pages/NotFound"));
const ContentEngine = lazy(() => import("./pages/ContentEngine"));

// Admin pages
const AdminAgentControl = lazy(() => import("./pages/admin/AgentControl"));
const AdminMCPTools = lazy(() => import("./pages/admin/MCPTools"));
const AdminMCPToolDetail = lazy(() => import("./pages/admin/MCPToolDetail"));
const AdminWorkflows = lazy(() => import("./pages/admin/Workflows"));
const AdminWorkflowRun = lazy(() => import("./pages/admin/WorkflowRunDetail"));
const AdminApprovals = lazy(() => import("./pages/admin/Approvals"));
const AdminApprovalDetail = lazy(() => import("./pages/admin/ApprovalDetail"));
const AdminContextPacks = lazy(() => import("./pages/admin/ContextPacks"));
const AdminContextPackDetail = lazy(() => import("./pages/admin/ContextPackDetail"));
const AdminWorkspaceExports = lazy(() => import("./pages/admin/WorkspaceExports"));
const AdminFunnelAnalytics = lazy(() => import("./pages/admin/FunnelAnalytics"));
const AdminAudit = lazy(() => import("./pages/admin/Audit"));
const AdminReadiness = lazy(() => import("./pages/admin/Readiness"));

function RouteFallback() {
  return (
    <div className="min-h-screen bg-gray-50 p-6 text-sm text-gray-600">
      Loading...
    </div>
  );
}

export function AppRoutes() {
  return (
    <Suspense fallback={<RouteFallback />}>
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
          <Route index element={<UnifiedDashboard />} />
          <Route path="approvals" element={<ApprovalQueue />} />
          <Route path="opportunities" element={<Opportunities />} />
          <Route path="drafts" element={<Drafts />} />
          <Route path="contacts" element={<Contacts />} />
          <Route path="leads" element={<Leads />} />
          <Route path="metrics" element={<Metrics />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="emails" element={<EmailThreads />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="costs" element={<Costs />} />
          <Route path="event-bus" element={<EventBus />} />
          <Route path="agents" element={<Agents />} />
          <Route path="content-engine" element={<ContentEngine />} />
          <Route path="settings" element={<Settings />} />
          {/* Admin routes */}
          <Route path="admin/agent-control" element={<AdminAgentControl />} />
          <Route path="admin/mcp-tools" element={<AdminMCPTools />} />
          <Route path="admin/mcp-tools/:name" element={<AdminMCPToolDetail />} />
          <Route path="admin/workflows" element={<AdminWorkflows />} />
          <Route path="admin/workflows/:run_id" element={<AdminWorkflowRun />} />
          <Route path="admin/approvals" element={<AdminApprovals />} />
          <Route path="admin/approvals/:id" element={<AdminApprovalDetail />} />
          <Route path="admin/context-packs" element={<AdminContextPacks />} />
          <Route path="admin/context-packs/:id" element={<AdminContextPackDetail />} />
          <Route path="admin/workspace-exports" element={<AdminWorkspaceExports />} />
          <Route path="admin/funnel/analytics" element={<AdminFunnelAnalytics />} />
          <Route path="admin/audit" element={<AdminAudit />} />
          <Route path="admin/readiness" element={<AdminReadiness />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Suspense>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
