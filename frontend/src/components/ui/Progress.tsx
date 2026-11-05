import { clsx } from 'clsx';

interface ProgressProps {
  value: number;
  className?: string;
  label?: string;
}

export function Progress({ value, className, label }: ProgressProps) {
  const pct = Math.min(100, Math.max(0, value));
  const colorClass =
    pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-500' : 'bg-red-500';

  return (
    <div className={clsx('w-full bg-slate-700 rounded-full h-2.5 overflow-hidden', className)}>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuetext={label ?? `${pct}% complete`}
        className={clsx(
          'h-full rounded-full motion-safe:transition-all motion-safe:duration-500',
          'motion-reduce:transition-none',
          colorClass,
        )}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
