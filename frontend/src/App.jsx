import { Routes, Route, Navigate } from 'react-router-dom';
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
import AiAdminPage      from './pages/AiAdminPage';
import DiagnosticPage   from './pages/DiagnosticPage';

function Protected({ children }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="flex items-center justify-center min-h-screen text-gray-400">Loading…</div>;
  return user ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={
          <Protected>
            <Layout>
              <Routes>
                <Route path="/"          element={<Dashboard />} />
                <Route path="/domains"   element={<DomainsPage />} />
                <Route path="/users"     element={<UsersPage />} />
                <Route path="/docker"    element={<DockerPage />} />
                <Route path="/services"     element={<ServicesPage />} />
                <Route path="/marketplace"  element={<MarketplacePage />} />
                <Route path="/admin-content" element={<AdminContentPage />} />
                <Route path="/dns"          element={<DnsPage />} />
                <Route path="/files"     element={<FilesPage />} />
                <Route path="/databases" element={<DatabasesPage />} />
                <Route path="/email"     element={<EmailPage />} />
                <Route path="/ssl"       element={<SslPage />} />
                <Route path="/security"  element={<SecurityPage />} />
                <Route path="/logs"      element={<LogsPage />} />
                <Route path="/backups"   element={<BackupsPage />} />
                <Route path="/terminal"  element={<TerminalPage />} />
                <Route path="/settings"      element={<SettingsPage />} />
                <Route path="/activity-log" element={<ActivityLogPage />} />
                <Route path="/menu"         element={<MenuPage />} />
                <Route path="/ai-admin"    element={<AiAdminPage />} />
                <Route path="/diagnostic"  element={<DiagnosticPage />} />
              </Routes>
            </Layout>
          </Protected>
        } />
      </Routes>
    </AuthProvider>
  );
}
