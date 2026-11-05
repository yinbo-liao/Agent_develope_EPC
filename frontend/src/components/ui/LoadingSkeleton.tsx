// Stable seed widths — avoids flickering from Math.random() in render
const SEED_WIDTHS = [82, 95, 68, 74, 88, 60, 91, 77, 85, 70, 93, 64, 79, 97, 72];

interface LoadingSkeletonProps {
  rows?: number;
  className?: string;
}

export function LoadingSkeleton({ rows = 5, className = '' }: LoadingSkeletonProps) {
  return (
    <div className={`space-y-3 ${className}`} role="status" aria-label="Loading" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 items-center animate-pulse">
          <div
            className="h-4 bg-slate-700 rounded flex-1"
            style={{ width: `${SEED_WIDTHS[i % SEED_WIDTHS.length]}%` }}
          />
          {i === 0 && <div className="h-4 bg-slate-700 rounded w-16 animate-pulse" />}
          {i === 0 && <div className="h-4 bg-slate-700 rounded w-20 animate-pulse" />}
        </div>
      ))}
      <span className="sr-only">Loading data...</span>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div
      className="rounded-xl border border-slate-800 bg-slate-900 p-4 animate-pulse"
      role="status"
      aria-label="Loading card"
      aria-busy="true"
    >
      <div className="h-5 bg-slate-700 rounded w-1/3 mb-3" />
      <div className="space-y-2">
        <div className="h-3 bg-slate-700 rounded w-full" />
        <div className="h-3 bg-slate-700 rounded w-4/5" />
      </div>
      <span className="sr-only">Loading...</span>
    </div>
  );
}

/** Table skeleton matching the typical data table layout. */
export function TableSkeleton({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-x-auto" role="status" aria-label="Loading table" aria-busy="true">
      <table className="w-full">
        <thead>
          <tr>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i} className="px-4 py-3"><div className="h-3 bg-slate-700 rounded w-20 animate-pulse" /></th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, row) => (
            <tr key={row}>
              {Array.from({ length: cols }).map((_, col) => (
                <td key={col} className="px-4 py-2.5">
                  <div
                    className="h-3 bg-slate-700 rounded animate-pulse"
                    style={{ width: `${SEED_WIDTHS[(row * cols + col) % SEED_WIDTHS.length]}%` }}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <span className="sr-only">Loading table data...</span>
    </div>
  );
}
