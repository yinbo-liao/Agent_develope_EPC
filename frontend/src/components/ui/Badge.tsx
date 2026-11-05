import { clsx } from 'clsx';
import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'destructive' | 'warning' | 'success' | 'info' | 'outline';

const variants: Record<BadgeVariant, string> = {
  default: 'bg-slate-700 text-slate-200',
  destructive: 'bg-red-900/60 text-red-300 border-red-700',
  warning: 'bg-amber-900/60 text-amber-300 border-amber-700',
  success: 'bg-emerald-900/60 text-emerald-300 border-emerald-700',
  info: 'bg-blue-900/60 text-blue-300 border-blue-700',
  outline: 'bg-transparent text-slate-400 border-slate-600',
};

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border border-slate-600',
      variants[variant],
      className,
    )}>
      {children}
    </span>
  );
}
