import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { TrendingDown, CheckCircle, XCircle } from 'lucide-react';

const NDT_COLORS: Record<string, string> = {
  UT: '#3b82f6',
  RT: '#8b5cf6',
  MT: '#10b981',
  PT: '#f59e0b',
  VT: '#06b6d4',
};

const STATUS_COLORS: Record<string, string> = {
  ACCEPTED: 'bg-emerald-500/10 text-emerald-400',
  WELDED: 'bg-blue-500/10 text-blue-400',
  PENDING_NDT: 'bg-slate-500/10 text-slate-400',
  NDT_PASSED: 'bg-cyan-500/10 text-cyan-400',
  NDT_FAILED: 'bg-red-500/10 text-red-400',
  REPAIRED: 'bg-amber-500/10 text-amber-400',
};

export function WeldRejectionAnalytics({ projectId }: { projectId: string }) {
  const { data: weldSummary } = useQuery({
    queryKey: ['weld-summary', projectId],
    queryFn: () => apiClient.get(`/api/quality/weld-summary/${projectId}`),
    refetchInterval: 60000,
  });

  const { data: welds } = useQuery({
    queryKey: ['welds', projectId],
    queryFn: () => apiClient.get(`/api/quality/welds/${projectId}`),
    refetchInterval: 30000,
  });

  const summaryData = weldSummary?.data || [];
  const weldList = welds?.data || [];

  // Status counts
  const statusCounts = weldList.reduce((acc: Record<string, number>, w: any) => {
    acc[w.status] = (acc[w.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <TrendingDown className="h-5 w-5 text-orange-400" />
        <h3 className="text-lg font-semibold text-white">Weld Rejection Analytics</h3>
      </div>

      {/* Rejection Rate Chart */}
      {summaryData.length > 0 && (
        <Card>
          <CardHeader><CardTitle className="text-sm">Rejection Rate by NDT Method</CardTitle></CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={summaryData} barCategoryGap="20%">
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="ndt_method" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={{ stroke: '#334155' }} />
                <YAxis
                  yAxisId="left"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  label={{ value: 'Count', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  domain={[0, 100]}
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  axisLine={{ stroke: '#334155' }}
                  label={{ value: 'Rejection %', angle: 90, position: 'insideRight', fill: '#ef4444', fontSize: 11 }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#f1f5f9' }}
                />
                <Bar yAxisId="left" dataKey="total_welds" name="Total Welds" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="left" dataKey="failed" name="NDT Failed" fill="#ef4444" radius={[4, 4, 0, 0]} />
                <Bar yAxisId="right" dataKey="rejection_rate_pct" name="Rejection Rate %" fill="#f59e0b" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            {/* Data Table below chart */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 mt-4">
              {summaryData.map((s: any) => (
                <div key={s.ndt_method} className="flex items-center justify-between p-2 rounded bg-slate-800/50">
                  <span className="text-xs font-semibold" style={{ color: NDT_COLORS[s.ndt_method] || '#94a3b8' }}>
                    {s.ndt_method}
                  </span>
                  <div className="flex items-center gap-2 text-[10px]">
                    <span className="text-slate-400">{s.total_welds} welds</span>
                    <span className="text-red-400 font-semibold">{s.rejection_rate_pct}%</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Status Overview + Weld List */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Status KPIs */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Status Breakdown</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(Object.entries(statusCounts) as [string, number][]).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${STATUS_COLORS[status] || 'text-slate-400'}`}>
                    {status?.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs font-bold text-white">{count}</span>
                </div>
              ))}
              <div className="pt-2 border-t border-slate-800 mt-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Total Welds</span>
                  <span className="text-white font-bold">{weldList.length}</span>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Weld Table */}
        <Card className="lg:col-span-3">
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-80 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Weld #</th>
                    <th className="text-left py-2 px-3 font-medium">Drawing</th>
                    <th className="text-center py-2 px-3 font-medium">Type</th>
                    <th className="text-center py-2 px-3 font-medium">Dia/Thk</th>
                    <th className="text-center py-2 px-3 font-medium">NDT Method</th>
                    <th className="text-center py-2 px-3 font-medium">Result</th>
                    <th className="text-center py-2 px-3 font-medium">Repairs</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {weldList.slice(0, 50).map((w: any) => (
                    <tr key={w.weld_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-3 font-mono text-slate-300">{w.weld_number}</td>
                      <td className="py-2 px-3 text-slate-400">{w.drawing_number || '—'}</td>
                      <td className="py-2 px-3 text-center text-slate-400">{w.weld_type || '—'}</td>
                      <td className="py-2 px-3 text-center text-slate-400">
                        {w.diameter_mm ? `${w.diameter_mm}mm / ${w.thickness_mm || '?'}mm` : '—'}
                      </td>
                      <td className="py-2 px-3 text-center">
                        {w.ndt_method
                          ? <span className="font-semibold" style={{ color: NDT_COLORS[w.ndt_method] || '#94a3b8' }}>{w.ndt_method}</span>
                          : <span className="text-slate-500">—</span>
                        }
                      </td>
                      <td className="py-2 px-3 text-center">
                        {w.ndt_result === 'ACCEPT'
                          ? <CheckCircle className="h-3.5 w-3.5 text-emerald-400 mx-auto" />
                          : w.ndt_result === 'REJECT'
                          ? <XCircle className="h-3.5 w-3.5 text-red-400 mx-auto" />
                          : <span className="text-slate-500">{w.ndt_result || '—'}</span>
                        }
                      </td>
                      <td className="py-2 px-3 text-center">
                        {(w.repair_count || 0) > 0
                          ? <Badge variant="destructive">{w.repair_count}</Badge>
                          : <span className="text-slate-500">0</span>
                        }
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_COLORS[w.status] || 'text-slate-400'}`}>
                          {w.status?.replace(/_/g, ' ')}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
