import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { Zap, CheckCircle, XCircle, Clock, Users, Eye } from 'lucide-react';

const PROCEDURE_TYPES = [
  { value: 'MC_CHECK', label: 'MC Check', icon: Eye },
  { value: 'PRE_COMM', label: 'Pre-Comm', icon: Clock },
  { value: 'COMM_PROCEDURE', label: 'Commissioning', icon: Zap },
  { value: 'PERFORMANCE_TEST', label: 'Performance Test', icon: CheckCircle },
];

const STATUS_COLORS: Record<string, string> = {
  PENDING: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  SCHEDULED: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  IN_PROGRESS: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  PASSED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  FAILED: 'bg-red-500/10 text-red-400 border-red-500/30',
  REVALIDATED: 'bg-purple-500/10 text-purple-400 border-purple-500/30',
};

export function CommissioningDashboard({ projectId }: { projectId: string }) {
  const [procType, setProcType] = useState<string | null>(null);
  const [selectedProcId, setSelectedProcId] = useState<string | null>(null);

  const { data: summary } = useQuery({
    queryKey: ['commissioning-summary', projectId],
    queryFn: () => apiClient.get(`/api/commissioning/summary/${projectId}`),
    refetchInterval: 30000,
  });

  const { data: procedures } = useQuery({
    queryKey: ['commissioning-procedures', projectId, procType],
    queryFn: () => {
      let url = `/api/commissioning/procedures/${projectId}`;
      if (procType) url += `?procedure_type=${procType}`;
      return apiClient.get(url);
    },
    refetchInterval: 30000,
  });

  const { data: checklist } = useQuery({
    queryKey: ['commissioning-checklist', selectedProcId],
    queryFn: () => apiClient.get(`/api/commissioning/checklist/${selectedProcId}`),
    enabled: !!selectedProcId,
  });

  const byProcType = summary?.data?.by_procedure_type || [];
  const bySystem = summary?.data?.by_system || [];
  const procList = procedures?.data || [];
  const checkItems = checklist?.data || [];

  // Calculate overall stats
  const totalProcs = byProcType.reduce((s: number, p: any) => s + (p.total || 0), 0);
  const totalPassed = byProcType.reduce((s: number, p: any) => s + (p.passed || 0), 0);
  const totalFailed = byProcType.reduce((s: number, p: any) => s + (p.failed || 0), 0);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Zap className="h-5 w-5 text-yellow-400" />
        <h3 className="text-lg font-semibold text-white">Commissioning Dashboard</h3>
      </div>

      {/* Overall KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Total Procedures</p>
            <p className="text-xl font-bold">{totalProcs}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Passed</p>
            <p className="text-xl font-bold text-emerald-400">{totalPassed}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Failed</p>
            <p className="text-xl font-bold text-red-400">{totalFailed}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide text-center mb-1">Completion</p>
            <Progress value={totalProcs > 0 ? (totalPassed / totalProcs * 100) : 0} className="h-2 mb-1" />
            <p className="text-[10px] text-slate-500 text-center">
              {totalProcs > 0 ? Math.round(totalPassed / totalProcs * 100) : 0}% passed
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Procedure Type Tabs */}
      <div className="flex gap-1 bg-slate-900 rounded-lg p-1 w-fit flex-wrap">
        <button
          onClick={() => setProcType(null)}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
            procType === null ? 'bg-primary/20 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          All
        </button>
        {PROCEDURE_TYPES.map(pt => {
          const Icon = pt.icon;
          const stats = byProcType.find((s: any) => s.procedure_type === pt.value);
          return (
            <button
              key={pt.value}
              onClick={() => setProcType(pt.value)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5 ${
                procType === pt.value ? 'bg-primary/20 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {pt.label}
              {stats && <span className="text-slate-600">({stats.passed || 0}/{stats.total || 0})</span>}
            </button>
          );
        })}
      </div>

      {/* By Type Summary Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {byProcType.map((pt: any) => (
          <Card key={pt.procedure_type}>
            <CardContent className="py-3">
              <div className="flex items-center justify-between mb-2">
                <p className="text-xs font-semibold text-white">{pt.procedure_type?.replace(/_/g, ' ')}</p>
                <span className="text-[10px] text-slate-500">{pt.total} total</span>
              </div>
              <div className="flex gap-2 text-[10px]">
                <span className="text-emerald-400 flex items-center gap-0.5"><CheckCircle className="h-3 w-3" /> {pt.passed || 0}</span>
                <span className="text-red-400 flex items-center gap-0.5"><XCircle className="h-3 w-3" /> {pt.failed || 0}</span>
                <span className="text-slate-400 flex items-center gap-0.5"><Clock className="h-3 w-3" /> {pt.pending || 0}</span>
              </div>
              <Progress
                value={pt.total > 0 ? ((pt.passed || 0) / pt.total * 100) : 0}
                className="h-1.5 mt-2"
              />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Procedures Table + Checklist Side-by-Side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Procedure List */}
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-sm">Procedures</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Code</th>
                    <th className="text-left py-2 px-3 font-medium">Name</th>
                    <th className="text-left py-2 px-3 font-medium">System</th>
                    <th className="text-center py-2 px-3 font-medium">Type</th>
                    <th className="text-center py-2 px-3 font-medium">Planned</th>
                    <th className="text-center py-2 px-3 font-medium">Actual</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                    <th className="text-center py-2 px-3 font-medium">Witness</th>
                  </tr>
                </thead>
                <tbody>
                  {procList.map((p: any) => (
                    <tr
                      key={p.procedure_id}
                      onClick={() => setSelectedProcId(p.procedure_id)}
                      className={`border-b border-slate-800/50 hover:bg-slate-800/30 cursor-pointer transition-colors ${
                        selectedProcId === p.procedure_id ? 'bg-slate-800/50 border-l-2 border-l-primary' : ''
                      }`}
                    >
                      <td className="py-2 px-3 font-mono text-slate-300">{p.procedure_code}</td>
                      <td className="py-2 px-3 text-slate-300 max-w-[180px] truncate" title={p.procedure_name}>{p.procedure_name}</td>
                      <td className="py-2 px-3 text-slate-400">{p.system_code}</td>
                      <td className="py-2 px-3 text-center">
                        <span className="text-slate-400">{p.procedure_type?.replace(/_/g, ' ')}</span>
                      </td>
                      <td className="py-2 px-3 text-center text-slate-400">{p.planned_date || '—'}</td>
                      <td className="py-2 px-3 text-center text-slate-400">{p.actual_date || '—'}</td>
                      <td className="py-2 px-3 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium border ${STATUS_COLORS[p.status] || ''}`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        {p.witness_required ? <Users className="h-3.5 w-3.5 text-amber-400 mx-auto" /> : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Checklist Panel */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Checklist</CardTitle></CardHeader>
          <CardContent>
            {!selectedProcId ? (
              <div className="text-center py-8 text-slate-500">
                <Eye className="h-8 w-8 text-slate-600 mx-auto mb-2" />
                <p className="text-xs">Select a procedure to view its checklist</p>
              </div>
            ) : checkItems.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <p className="text-xs">No checklist items</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {checkItems.map((ci: any) => (
                  <div key={ci.checklist_id} className={`p-2.5 rounded-lg border ${ci.is_verified ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-slate-800 bg-slate-800/30'}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-[10px] font-mono text-slate-500">#{ci.item_number}</span>
                          <p className="text-xs text-slate-300">{ci.check_description}</p>
                        </div>
                        {ci.expected_result && (
                          <p className="text-[10px] text-slate-500 ml-8">Expected: {ci.expected_result}</p>
                        )}
                        {ci.actual_result && (
                          <p className={`text-[10px] ml-8 ${ci.is_verified ? 'text-emerald-400' : 'text-slate-400'}`}>
                            Actual: {ci.actual_result}
                          </p>
                        )}
                      </div>
                      {ci.is_verified ? (
                        <CheckCircle className="h-4 w-4 text-emerald-400 shrink-0" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-slate-700 shrink-0" />
                      )}
                    </div>
                    {ci.verified_by && (
                      <p className="text-[10px] text-slate-500 mt-1 ml-8">
                        Verified by {ci.verified_by} {ci.verified_date ? `on ${ci.verified_date.slice(0, 10)}` : ''}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* System-Level Progress */}
      {bySystem.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">System Commissioning Progress</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-3">
              {bySystem.map((sys: any) => (
                <div key={sys.system_code}>
                  <div className="flex items-center justify-between mb-1">
                    <div>
                      <span className="text-xs font-mono text-slate-300">{sys.system_code}</span>
                      <span className="text-xs text-slate-500 ml-2">{sys.system_name}</span>
                    </div>
                    <span className="text-xs text-slate-400">
                      {sys.passed || 0}/{sys.total_procedures || 0} passed
                    </span>
                  </div>
                  <Progress
                    value={sys.total_procedures > 0 ? ((sys.passed || 0) / sys.total_procedures * 100) : 0}
                    className="h-1.5"
                  />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
