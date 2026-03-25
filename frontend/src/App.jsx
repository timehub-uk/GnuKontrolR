import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import ErrorBoundary from './components/ErrorBoundary';
import { AnimatePresence, motion } from 'framer-motion';
import { QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { queryClient } from './utils/queryClient';
import { AuthProvider, useAuth } from './context/AuthContext';
import Layout from './components/Layout';
import LoginPage         from './pages/LoginPage';
import Dashboard         from './pages/Dashboard';
import DomainsPage       from './pages/DomainsPage';
import UsersPage         from './pages/UsersPage';
import DockerPage        from './pages/DockerPage';
import ServicesPage      from './pages/ServicesPage';
import MarketplacePage   from './pages/MarketplacePage';
import DnsPage           from './pages/DnsPage';
import FilesPage         from './pages/FilesPage';
import DatabasesPage     from './pages/DatabasesPage';
import EmailPage         from './pages/EmailPage';
import SslPage           from './pages/SslPage';
import LogsPage          from './pages/LogsPage';
import BackupsPage       from './pages/BackupsPage';
import TerminalPage      from './pages/TerminalPage';
import SettingsPage      from './pages/SettingsPage';
import AdminContentPage  from './pages/AdminContentPage';
import ActivityLogPage   from './pages/ActivityLogPage';
import SecurityPage      from './pages/SecurityPage';
import MenuPage          from './pages/MenuPage';
import AiAdminPage       from './pages/AiAdminPage';
import DiagnosticPage    from './pages/DiagnosticPage';

const pageTransition = {
  initial:    { opacity: 0, y: 8 },
  animate:    { opacity: 1, y: 0 },
  exit:       { opacity: 0, y: -8 },
  transition: { duration: 0.18, ease: 'easeOut' },
};

function Pg({ children }) {
  return (
    <motion.div {...pageTransition} className="h-full">
      <ErrorBoundary>{children}</ErrorBoundary>
    </motion.div>
  );
}

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <Routes location={location} key={location.pathname}>
        <Route path="/"              element={<Pg><Dashboard /></Pg>} />
        <Route path="/domains"       element={<Pg><DomainsPage /></Pg>} />
        <Route path="/users"         element={<Pg><UsersPage /></Pg>} />
        <Route path="/docker"        element={<Pg><DockerPage /></Pg>} />
        <Route path="/services"      element={<Pg><ServicesPage /></Pg>} />
        <Route path="/marketplace"   element={<Pg><MarketplacePage /></Pg>} />
        <Route path="/admin-content" element={<Pg><AdminContentPage /></Pg>} />
        <Route path="/dns"           element={<Pg><DnsPage /></Pg>} />
        <Route path="/files"         element={<Pg><FilesPage /></Pg>} />
        <Route path="/databases"     element={<Pg><DatabasesPage /></Pg>} />
        <Route path="/email"         element={<Pg><EmailPage /></Pg>} />
        <Route path="/ssl"           element={<Pg><SslPage /></Pg>} />
        <Route path="/security"      element={<Pg><SecurityPage /></Pg>} />
        <Route path="/logs"          element={<Pg><LogsPage /></Pg>} />
        <Route path="/backups"       element={<Pg><BackupsPage /></Pg>} />
        <Route path="/terminal"      element={<Pg><TerminalPage /></Pg>} />
        <Route path="/settings"      element={<Pg><SettingsPage /></Pg>} />
        <Route path="/activity-log"  element={<Pg><ActivityLogPage /></Pg>} />
        <Route path="/menu"          element={<Pg><MenuPage /></Pg>} />
        <Route path="/ai-admin"      element={<Pg><AiAdminPage /></Pg>} />
        <Route path="/diagnostic"    element={<Pg><DiagnosticPage /></Pg>} />
      </Routes>
    </AnimatePresence>
  );
}

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="w-8 h-8 border-2 border-brand border-t-transparent rounded-full animate-spin" />
    </div>
  );
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Toaster position="bottom-right" theme="dark" richColors closeButton />
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/*" element={
            <Protected>
              <Layout>
                <AnimatedRoutes />
              </Layout>
            </Protected>
          } />
        </Routes>
      </AuthProvider>
    </QueryClientProvider>
  );
}
