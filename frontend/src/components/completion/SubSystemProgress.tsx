import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { Layers, Filter, ChevronRight } from 'lucide-react';
import { TableSkeleton } from '../ui/LoadingSkeleton';

const STATUS_COLORS: Record<string, string> = {
  NOT_STARTED: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  IN_PROGRESS: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  READY_FOR_MC: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  MC_COMPLETE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  HANDED_OVER: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
};

const DISCIPLINE_COLORS: Record<string, string> = {
  STRUCTURAL: '#3b82f6',
  PIPING: '#8b5cf6',
  MECHANICAL: '#f59e0b',
  ELECTRICAL: '#10b981',
  HVAC: '#06b6d4',
  ARCHITECTURE_DECORATION: '#ec4899',
};

export function SubSystemProgress({ projectId }: { projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [disciplineFilter, setDisciplineFilter] = useState<string | null>(null);

  const { data: subsystems, isLoading } = useQuery({
    queryKey: ['sub-systems', projectId, statusFilter, disciplineFilter],
    queryFn: () => {
      let url = `/api/completion/sub-systems/${projectId}`;
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (disciplineFilter) params.set('discipline_id', disciplineFilter);
      const qs = params.toString();
      return apiClient.get(qs ? `${url}?${qs}` : url);
    },
    refetchInterval: 30000,
  });

  const items = subsystems?.data || [];

  // Group by discipline
  const grouped: Record<string, any[]> = {};
  items.forEach((ss: any) => {
    const d = ss.discipline_name || 'Unassigned';
    if (!grouped[d]) grouped[d] = [];
    grouped[d].push(ss);
  });

  const statusCounts = items.reduce((acc: Record<string, number>, ss: any) => {
    acc[ss.completion_status] = (acc[ss.completion_status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Layers className="h-5 w-5 text-purple-400" />
        <h3 className="text-lg font-semibold text-white">Sub-System Progress</h3>
      </div>

      {/* Status KPI cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {[
          { key: 'NOT_STARTED', label: 'Not Started' },
          { key: 'IN_PROGRESS', label: 'In Progress' },
          { key: 'READY_FOR_MC', label: 'Ready for MC' },
          { key: 'MC_COMPLETE', label: 'MC Complete' },
          { key: 'HANDED_OVER', label: 'Handed Over' },
        ].map(s => (
          <Card key={s.key} className={statusFilter === s.key ? 'ring-1 ring-primary' : ''}>
            <button onClick={() => setStatusFilter(statusFilter === s.key ? null : s.key)} className="w-full text-left">
              <CardContent className="py-3">
                <p className="text-[10px] text-slate-400 uppercase tracking-wide">{s.label}</p>
                <p className="text-xl font-bold">{statusCounts[s.key] || 0}</p>
              </CardContent>
            </button>
          </Card>
        ))}
      </div>

      {/* Total progress */}
      <Card>
        <CardContent className="py-3">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Overall Completion</span>
            <span className="text-xs font-mono text-white">
              {items.length > 0
                ? Math.round((statusCounts['HANDED_OVER'] || 0) / items.length * 100)
                : 0}%
            </span>
          </div>
          <Progress
            value={items.length > 0 ? ((statusCounts['HANDED_OVER'] || 0) / items.length * 100) : 0}
            className="h-2"
          />
        </CardContent>
      </Card>

      {/* Discipline Groups */}
      {isLoading ? (
        <TableSkeleton rows={6} cols={4} />
      ) : (
        Object.entries(grouped).map(([discipline, systems]) => (
          <Card key={discipline}>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: DISCIPLINE_COLORS[discipline] || '#64748b' }} />
                  <CardTitle className="text-sm">{discipline}</CardTitle>
                  <Badge variant="default">{systems.length} systems</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-800">
                      <th className="text-left py-2 px-3 font-medium">System Code</th>
                      <th className="text-left py-2 px-3 font-medium">System Name</th>
                      <th className="text-left py-2 px-3 font-medium">Area</th>
                      <th className="text-center py-2 px-3 font-medium">Status</th>
                      <th className="text-center py-2 px-3 font-medium">Planned MC</th>
                      <th className="text-center py-2 px-3 font-medium">Actual MC</th>
                      <th className="text-center py-2 px-3 font-medium">Open Punches</th>
                      <th className="text-left py-2 px-3 font-medium">Engineer</th>
                    </tr>
                  </thead>
                  <tbody>
                    {systems.map((ss: any) => (
                      <tr key={ss.sub_system_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="py-2 px-3 font-mono text-slate-300">{ss.system_code}</td>
                        <td className="py-2 px-3 text-slate-300">{ss.system_name}</td>
                        <td className="py-2 px-3 text-slate-400">{ss.area_code || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium border ${STATUS_COLORS[ss.completion_status] || 'text-slate-400'}`}>
                            {ss.completion_status?.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-center text-slate-400">{ss.planned_mc_date || '—'}</td>
                        <td className="py-2 px-3 text-center text-slate-400">{ss.actual_mc_date || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          {(ss.open_punch_count || 0) > 0
                            ? <Badge variant="destructive">{ss.open_punch_count}</Badge>
                            : <span className="text-slate-500">0</span>
                          }
                        </td>
                        <td className="py-2 px-3 text-slate-400">{ss.responsible_engineer || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}
