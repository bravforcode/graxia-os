import { Suspense, lazy } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { PageTransition } from "./components/ui/PageTransition";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Layout from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AuthProvider } from "./contexts/AuthContext";
import { LanguageProvider } from "./i18n/LanguageContext";
import ExitIntentPopup from "./components/ui/ExitIntentPopup";
import SocialProofPopup from "./components/ui/SocialProofPopup";

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
const LandingPage = lazy(() => import("./pages/LandingPage"));
const StorePage = lazy(() => import("./pages/StorePage"));
const StoreProductPage = lazy(() => import("./pages/StoreProductPage"));

// Funnel Pages
const ProductList = lazy(() => import("./pages/funnel/ProductList"));
const ProductEditor = lazy(() => import("./pages/funnel/ProductEditor"));
const PublicProductPage = lazy(() => import("./pages/funnel/PublicProductPage"));
const CheckoutSuccess = lazy(() => import("./pages/funnel/CheckoutSuccess"));
const DeliveryAccessPage = lazy(() => import("./pages/funnel/DeliveryAccessPage"));
const FunnelAnalytics = lazy(() => import("./pages/funnel/FunnelAnalytics"));

function RouteFallback() {
  return (
    <div className="min-h-screen bg-slate-950 p-6 text-sm text-slate-400">
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
        <Route path="/store" element={<PageTransition><StorePage /></PageTransition>} />
        <Route path="/store/:slug" element={<PageTransition><StoreProductPage /></PageTransition>} />
        <Route path="/f/:organization_id/:slug" element={<PublicProductPage />} />
        <Route path="/checkout/success" element={<CheckoutSuccess />} />
        <Route path="/delivery/:token" element={<DeliveryAccessPage />} />

        {/* Protected routes */}
        <Route path="/" element={<PageTransition><LandingPage /></PageTransition>} />
        <Route
          path="/app"
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
          <Route path="settings" element={<Settings />} />
          
          {/* Funnel Routes */}
          <Route path="products" element={<ProductList />} />
          <Route path="products/:id" element={<ProductEditor />} />
          <Route path="funnel/analytics" element={<FunnelAnalytics />} />
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
        <LanguageProvider>
          <AuthProvider>
            <AppRoutes />
            <ExitIntentPopup />
            <SocialProofPopup />
          </AuthProvider>
        </LanguageProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}

export default App;
