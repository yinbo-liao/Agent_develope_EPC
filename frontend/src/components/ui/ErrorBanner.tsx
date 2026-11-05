import { AlertTriangle, XCircle, RefreshCw } from 'lucide-react';
import { Button } from './Button';

interface ErrorBannerProps {
  title?: string;
  message: string;
  variant?: 'error' | 'warning';
  onRetry?: () => void;
}

export function ErrorBanner({ title = 'Error', message, variant = 'error', onRetry }: ErrorBannerProps) {
  const isError = variant === 'error';

  return (
    <div className={`rounded-lg border p-4 ${
      isError
        ? 'bg-red-500/10 border-red-500/30 text-red-300'
        : 'bg-amber-500/10 border-amber-500/30 text-amber-300'
    }`}>
      <div className="flex items-start gap-3">
        {isError
          ? <XCircle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
          : <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
        }
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold">{title}</p>
          <p className="text-xs opacity-80 mt-0.5">{message}</p>
        </div>
        {onRetry && (
          <Button onClick={onRetry} className="text-xs px-3 py-1.5 shrink-0">
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
