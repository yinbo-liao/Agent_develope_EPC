import { Routes, Route, Navigate } from 'react-router-dom';
import { Dashboard } from './pages/Dashboard';
import { PanelErrorBoundary } from './components/ui/ErrorBoundary';

export default function App() {
  return (
    <Routes>
      <Route
        path="/projects/:projectId"
        element={
          <PanelErrorBoundary title="Dashboard Error">
            <Dashboard />
          </PanelErrorBoundary>
        }
      />
      <Route path="*" element={<Navigate to="/projects/demo-project" replace />} />
    </Routes>
  );
}
