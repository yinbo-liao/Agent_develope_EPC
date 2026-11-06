import { Routes, Route, Navigate } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { LoginPage } from './pages/LoginPage';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { PanelErrorBoundary } from './components/ui/ErrorBoundary';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/projects/:projectId"
        element={
          <ProtectedRoute>
            <PanelErrorBoundary title="Dashboard Error">
              <Dashboard />
            </PanelErrorBoundary>
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate to="/projects/demo-project" replace />} />
      <Route path="*" element={<Navigate to="/projects/demo-project" replace />} />
    </Routes>
  );
}
