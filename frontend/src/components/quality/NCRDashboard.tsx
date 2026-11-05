import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { Shield, AlertTriangle, Clock, Filter } from 'lucide-react';

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-red-600/20 text-red-400 border-red-600/40',
  MAJOR: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  MINOR: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  OBSERVATION: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: 'bg-red-500/10 text-red-400 border-red-500/30',
  UNDER_INVESTIGATION: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  CORRECTIVE_ACTION: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  PENDING_VERIFICATION: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
  CLOSED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
};

export function NCRDashboard({ projectId }: { projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);

  const { data: ncrs, isLoading } = useQuery({
    queryKey: ['ncrs', projectId, statusFilter, severityFilter],
    queryFn: () => {
      let url = `/api/quality/ncr/${projectId}`;
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (severityFilter) params.set('severity', severityFilter);
      const qs = params.toString();
      return apiClient.get(qs ? `${url}?${qs}` : url);
    },
    refetchInterval: 30000,
  });

  const { data: summary } = useQuery({
    queryKey: ['ncr-summary', projectId],
    queryFn: () => apiClient.get(`/api/quality/ncr-summary/${projectId}`),
    refetchInterval: 30000,
  });

  const items = ncrs?.data || [];
  const sum = summary?.data || {};

  const now = new Date();
  const getAge = (d: string) => d ? Math.floor((now.getTime() - new Date(d).getTime()) / 86400000) : 0;

  const bySeverity = sum.by_severity || [];
  const byDiscipline = sum.by_discipline || [];
  const aging = sum.aging || [];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Shield className="h-5 w-5 text-red-400" />
        <h3 className="text-lg font-semibold text-white">NCR Dashboard</h3>
      </div>

      {/* Severity Summary */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {bySeverity.map((s: any) => (
          <Card key={s.severity} className={severityFilter === s.severity ? 'ring-1 ring-primary' : ''}>
            <button onClick={() => setSeverityFilter(severityFilter === s.severity ? null : s.severity)} className="w-full text-left">
              <CardContent className="py-3">
                <div className="flex items-center justify-between">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${SEVERITY_COLORS[s.severity] || ''}`}>
                    {s.severity}
                  </span>
                  <span className="text-[10px] text-slate-500">{s.count} total</span>
                </div>
                <p className="text-lg font-bold mt-1">{s.closed || 0} closed</p>
                <Progress value={s.count > 0 ? (s.closed / s.count * 100) : 0} className="h-1.5 mt-1" />
              </CardContent>
            </button>
          </Card>
        ))}
      </div>

      {/* Aging & Discipline Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Aging */}
        <Card>
          <CardHeader><CardTitle className="text-sm">NCR Aging (Open)</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {aging.map((a: any) => (
                <div key={a.age_bucket} className="flex items-center justify-between">
                  <span className="text-xs text-slate-400">{a.age_bucket}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-white">{a.count}</span>
                    <Progress value={aging.length > 0 ? (a.count / Math.max(...aging.map((x: any) => x.count || 1)) * 100) : 0} className="w-16 h-1.5" />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* By Discipline */}
        <Card>
          <CardHeader><CardTitle className="text-sm">By Discipline</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {byDiscipline.map((d: any) => (
                <div key={d.discipline_name}>
                  <div className="flex items-center justify-between mb-0.5">
                    <span className="text-xs text-slate-400">{d.discipline_name}</span>
                    <span className="text-[10px] text-slate-500">{d.closed}/{d.count} closed</span>
                  </div>
                  <Progress value={d.count > 0 ? (d.closed / d.count * 100) : 0} className="h-1.5" />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* NCR List */}
      {isLoading ? (
        <div className="text-center py-10 text-slate-500">Loading NCRs...</div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">NCR #</th>
                    <th className="text-center py-2 px-3 font-medium">Severity</th>
                    <th className="text-left py-2 px-3 font-medium">Description</th>
                    <th className="text-left py-2 px-3 font-medium">Discipline</th>
                    <th className="text-left py-2 px-3 font-medium">System</th>
                    <th className="text-center py-2 px-3 font-medium">Raised</th>
                    <th className="text-center py-2 px-3 font-medium">Age</th>
                    <th className="text-center py-2 px-3 font-medium">Target</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((ncr: any) => {
                    const age = getAge(ncr.raised_date);
                    return (
                      <tr key={ncr.ncr_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                        <td className="py-2 px-3 font-mono text-slate-300">{ncr.ncr_number}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${SEVERITY_COLORS[ncr.severity] || ''}`}>
                            {ncr.severity}
                          </span>
                        </td>
                        <td className="py-2 px-3 text-slate-300 max-w-[200px] truncate" title={ncr.description}>{ncr.description}</td>
                        <td className="py-2 px-3 text-slate-400">{ncr.discipline_name || '—'}</td>
                        <td className="py-2 px-3 text-slate-400">{ncr.system_code || '—'}</td>
                        <td className="py-2 px-3 text-center text-slate-400">{ncr.raised_date || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          {age > 30 ? <span className="text-red-400 font-semibold">{age}d</span>
                            : age > 14 ? <span className="text-amber-400">{age}d</span>
                            : <span className="text-slate-400">{age}d</span>}
                        </td>
                        <td className="py-2 px-3 text-center text-slate-400">{ncr.target_closeout_date || '—'}</td>
                        <td className="py-2 px-3 text-center">
                          <span className={`inline-block px-2 py-0.5 rounded text-[10px] border ${STATUS_COLORS[ncr.status] || ''}`}>
                            {ncr.status?.replace(/_/g, ' ')}
                          </span>
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
