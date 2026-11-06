import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { useAuth } from './context';

interface ProtectedRouteProps {
  children: ReactNode;
}

/**
 * Gate for authenticated routes. Renders a full-page loader while the session
 * is being restored, then redirects unauthenticated users to /login keeping
 * the original location for post-login navigation.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div
        className="min-h-screen bg-slate-950 flex items-center justify-center"
        role="status"
        aria-live="polite"
        aria-busy="true"
        aria-label="Checking authentication"
      >
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 text-primary-light animate-spin" aria-hidden="true" />
          <p className="text-sm text-slate-400">Checking authentication</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  return <>{children}</>;
}
