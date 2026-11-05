import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { ClipboardList, AlertCircle, Clock } from 'lucide-react';
import { TableSkeleton } from '../ui/LoadingSkeleton';

const CATEGORY_COLORS: Record<string, string> = {
  A: 'bg-red-500/10 text-red-400 border-red-500/30',
  B: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  C: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

const PRIORITY_ORDER: Record<string, number> = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

export function PunchListTracker({ projectId }: { projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);

  const { data: punches, isLoading } = useQuery({
    queryKey: ['punch-items', projectId, statusFilter, categoryFilter],
    queryFn: () => {
      let url = `/api/completion/punch-items/${projectId}`;
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (categoryFilter) params.set('category', categoryFilter);
      const qs = params.toString();
      return apiClient.get(qs ? `${url}?${qs}` : url);
    },
    refetchInterval: 30000,
  });

  const { data: summary } = useQuery({
    queryKey: ['punch-summary', projectId],
    queryFn: () => apiClient.get(`/api/completion/punch-summary/${projectId}`),
    refetchInterval: 30000,
  });

  const items = punches?.data || [];
  const sum = summary?.data || {};

  const now = new Date();
  const getAgeDays = (raisedDate: string) => {
    if (!raisedDate) return 0;
    return Math.floor((now.getTime() - new Date(raisedDate).getTime()) / 86400000);
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ClipboardList className="h-5 w-5 text-amber-400" />
        <h3 className="text-lg font-semibold text-white">Punch List Tracker</h3>
      </div>

      {/* Summary KPI */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Total Punches</p>
            <p className="text-xl font-bold">{sum.total || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Closed</p>
            <p className="text-xl font-bold text-emerald-400">{sum.total_closed || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Closeout %</p>
            <p className="text-xl font-bold">{sum.closeout_pct || 0}%</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3">
            <Progress value={sum.closeout_pct || 0} className="h-2 mb-1" />
            <p className="text-[10px] text-slate-500 text-center">Overall Closeout Progress</p>
          </CardContent>
        </Card>
      </div>

      {/* Category breakdown */}
      {sum.by_category && (
        <div className="grid gap-3 sm:grid-cols-3">
          {sum.by_category.map((cat: any) => (
            <Card key={cat.category} className={categoryFilter === cat.category ? 'ring-1 ring-primary' : ''}>
              <button onClick={() => setCategoryFilter(categoryFilter === cat.category ? null : cat.category)} className="w-full text-left">
                <CardContent className="py-3">
                  <div className="flex items-center justify-between">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${CATEGORY_COLORS[cat.category] || ''}`}>
                      CAT {cat.category}
                    </span>
                    <span className="text-xs text-slate-400">
                      {cat.closed}/{cat.count} closed
                    </span>
                  </div>
                  <Progress
                    value={cat.count > 0 ? (cat.closed / cat.count * 100) : 0}
                    className="h-1.5 mt-2"
                  />
                </CardContent>
              </button>
            </Card>
          ))}
        </div>
      )}

      {/* Punch Items Table */}
      {isLoading ? (
        <TableSkeleton rows={5} cols={5} />
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <ClipboardList className="h-10 w-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No punch items found</p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Punch #</th>
                    <th className="text-left py-2 px-3 font-medium">System</th>
                    <th className="text-center py-2 px-3 font-medium">Cat</th>
                    <th className="text-left py-2 px-3 font-medium">Description</th>
                    <th className="text-left py-2 px-3 font-medium">Discipline</th>
                    <th className="text-left py-2 px-3 font-medium">Raised By</th>
                    <th className="text-center py-2 px-3 font-medium">Age (Days)</th>
                    <th className="text-center py-2 px-3 font-medium">Target Date</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((p: any) => {
                    const ageDays = getAgeDays(p.raised_date);
                    return (
                      <tr key={p.punch_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="py-2 px-3 font-mono text-slate-300">{p.punch_number || '—'}</td>
                        <td className="py-2 px-3 text-slate-300 max-w-[140px] truncate" title={p.system_name}>{p.system_code}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold border ${CATEGORY_COLORS[p.category] || ''}`}>
                            {p.category}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-300 max-w-[250px] truncate" title={p.description}>{p.description}</td>
                        <td className="py-2 px-3 text-slate-400">{p.discipline_name || '—'}</td>
                        <td className="py-2 px-3 text-slate-400">{p.raised_by || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          {ageDays > 14
                            ? <span className="text-red-400 font-semibold flex items-center justify-center gap-1"><Clock className="h-3 w-3" /> {ageDays}d</span>
                            : ageDays > 7
                            ? <span className="text-amber-400">{ageDays}d</span>
                            : <span className="text-slate-400">{ageDays}d</span>
                          }
                        </td>
                        <td className="py-2 px-3 text-center text-slate-400">{p.target_date || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          {p.status === 'CLOSED'
                            ? <Badge variant="success">Closed</Badge>
                            : p.status === 'IN_PROGRESS'
                            ? <Badge variant="warning">In Progress</Badge>
                            : <Badge variant="default">{p.status}</Badge>
                          }
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
