import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ErrorBanner } from '../ui/ErrorBanner';
import { TableSkeleton } from '../ui/LoadingSkeleton';
import { apiClient } from '../../lib/api-client';
import type { DrawingMaterial } from '../../types/api';

interface MaterialConfirmationTabProps {
  projectId: string;
  materials: DrawingMaterial[];
  isLoading: boolean;
  isError: boolean;
  onRefetch: () => void;
  onMvrUpdate: () => void;
}

const MVR_STATUSES = ['Info-AFI', 'Structure-requested', 'piping-requested', 'PR-Raised', 'MVR-confirm'] as const;

const MVR_VARIANT: Record<string, 'default' | 'warning' | 'success' | 'info'> = {
  'Info-AFI': 'info',
  'Structure-requested': 'warning',
  'piping-requested': 'warning',
  'PR-Raised': 'success',
  'MVR-confirm': 'success',
};

export function MaterialConfirmationTab({
  projectId, materials, isLoading, isError, onRefetch, onMvrUpdate,
}: MaterialConfirmationTabProps) {
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [message, setMessage] = useState<string | null>(null);

  const handleConfirmMvr = async (materialId: string, newStatus: string) => {
    setSaving((prev) => ({ ...prev, [materialId]: true }));
    try {
      const res = await apiClient.patch(`/api/construction/mvr-status/${materialId}`, {
        mvr_status: newStatus,
        confirmed_by: 'Trade Leader',
      });
      const msg = res.data?.message || res.data?.status || '';
      setMessage(msg.includes('error') ? null : `MVR status updated to ${newStatus}`);
      onMvrUpdate();
    } catch {
      setMessage('Failed to update MVR status');
    } finally {
      setSaving((prev) => ({ ...prev, [materialId]: false }));
      setTimeout(() => setMessage(null), 4000);
    }
  };

  if (isLoading) return <TableSkeleton rows={8} cols={6} />;

  if (isError) {
    return (
      <ErrorBanner
        title="Failed to load materials"
        message="Could not retrieve construction materials from the server."
        onRetry={onRefetch}
      />
    );
  }

  if (!materials.length) {
    return (
      <Card>
        <CardContent>
          <p className="text-slate-400 text-center py-8">No materials found for MVR confirmation.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {message && (
        <div className={`rounded-lg p-3 text-sm ${message.includes('Failed') ? 'bg-red-500/10 text-red-300 border border-red-500/30' : 'bg-emerald-500/10 text-emerald-300 border border-emerald-500/30'}`}>
          {message}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Material Verification Request (MVR) — Confirmation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-left">
                  <th className="py-2 px-3">Piece Mark</th>
                  <th className="py-2 px-3">Material Grade</th>
                  <th className="py-2 px-3">Type</th>
                  <th className="py-2 px-3">Size/OD</th>
                  <th className="py-2 px-3">MVR Status</th>
                  <th className="py-2 px-3">PO Status</th>
                  <th className="py-2 px-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {materials.map((m, idx) => (
                  <tr key={m.material_id ?? idx} className="border-b border-slate-800 hover:bg-slate-800/30">
                    <td className="py-2 px-3 font-mono text-xs">{m.piece_mark ?? '-'}</td>
                    <td className="py-2 px-3 text-xs">{m.material_grade ?? '-'}</td>
                    <td className="py-2 px-3"><Badge>{m.material_type ?? '-'}</Badge></td>
                    <td className="py-2 px-3 text-xs">{m.size || m.diameter || '-'}</td>
                    <td className="py-2 px-3">
                      <Badge variant={MVR_VARIANT[m.mvr_status ?? ''] ?? 'default'}>
                        {m.mvr_status ?? 'Info-AFI'}
                      </Badge>
                    </td>
                    <td className="py-2 px-3 text-xs">{m.po_status || '-'}</td>
                    <td className="py-2 px-3">
                      <div className="flex gap-1 flex-wrap">
                        {MVR_STATUSES.filter((s) => s !== m.mvr_status).slice(0, 2).map((s) => (
                          <Button
                            key={s}
                            onClick={() => handleConfirmMvr(m.material_id!, s)}
                            disabled={saving[m.material_id!]}
                            className="text-[10px] px-2 py-1"
                          >
                            {s}
                          </Button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
