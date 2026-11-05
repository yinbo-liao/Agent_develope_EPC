import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { apiClient } from '../../lib/api-client';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { Siren, AlertTriangle, ShieldCheck, Clock, Users, Construction } from 'lucide-react';

const INCIDENT_COLORS: Record<string, string> = {
  LTI: '#ef4444',
  MTI: '#f97316',
  RWC: '#eab308',
  FA: '#3b82f6',
  NEAR_MISS: '#8b5cf6',
  OBSERVATION: '#94a3b8',
  FIRST_AID: '#10b981',
};

export function SafetyDashboard({ projectId }: { projectId: string }) {
  const [incidentType, setIncidentType] = useState<string | null>(null);

  const { data: hseStats } = useQuery({
    queryKey: ['hse-stats', projectId],
    queryFn: () => apiClient.get(`/api/safety/hse-stats/${projectId}`),
    refetchInterval: 30000,
  });

  const { data: incidents } = useQuery({
    queryKey: ['incidents', projectId, incidentType],
    queryFn: () => {
      let url = `/api/safety/incidents/${projectId}`;
      if (incidentType) url += `?incident_type=${incidentType}`;
      return apiClient.get(url);
    },
    refetchInterval: 30000,
  });

  /**/
  const { data: permits } = useQuery({
    queryKey: ['permits', projectId],
    queryFn: () => apiClient.get(`/api/safety/permits/${projectId}`),
    refetchInterval: 30000,
  });

  const stats = hseStats?.data || {};
  const incidentList = incidents?.data || [];
  const permitList = permits?.data || [];

  // Build trend data (simplified: group incidents by month)
  const trendData = incidentList.reduce((acc: Record<string, any>, i: any) => {
    const month = i.incident_date?.slice(0, 7) || 'Unknown';
    if (!acc[month]) acc[month] = { month, LTI: 0, MTI: 0, FA: 0, NEAR_MISS: 0, total: 0 };
    acc[month][i.incident_type] = (acc[month][i.incident_type] || 0) + 1;
    acc[month].total += 1;
    return acc;
  }, {});

  const trendArray = Object.values(trendData).sort((a: any, b: any) => a.month.localeCompare(b.month));

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Siren className="h-5 w-5 text-red-400" />
        <h3 className="text-lg font-semibold text-white">Safety (HSE) Dashboard</h3>
      </div>

      {/* HSE KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">TRIR</p>
            <p className={`text-xl font-bold ${stats.trir > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
              {stats.trir || 0}
            </p>
            <p className="text-[10px] text-slate-600">per 200k hrs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">LTIFR</p>
            <p className={`text-xl font-bold ${stats.ltifr > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
              {stats.ltifr || 0}
            </p>
            <p className="text-[10px] text-slate-600">per 1M hrs</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Safe Man-Hours</p>
            <p className="text-xl font-bold text-blue-400">
              {stats.safe_man_hours ? (stats.safe_man_hours / 1000000).toFixed(1) + 'M' : '0'}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">LTI Count</p>
            <p className={`text-xl font-bold ${stats.lti_count > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
              {stats.lti_count || 0}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Near Misses</p>
            <p className="text-xl font-bold text-purple-400">{stats.near_miss_count || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Incident Trend Chart + Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle className="text-sm">Incident Trend</CardTitle></CardHeader>
          <CardContent>
            {trendArray.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={trendArray}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="month" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#334155' }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#334155' }} allowDecimals={false} />
                  <Tooltip contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="LTI" stroke="#ef4444" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="MTI" stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="FA" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                  <Line type="monotone" dataKey="NEAR_MISS" stroke="#8b5cf6" strokeWidth={2} dot={{ r: 3 }} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-center py-10 text-slate-500">No incident data available</div>
            )}
          </CardContent>
        </Card>

        {/* Incident Type Breakdown */}
        <Card>
          <CardHeader><CardTitle className="text-sm">By Type</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              {Object.entries(INCIDENT_COLORS).map(([itype, color]) => {
                const count = incidentList.filter((i: any) => i.incident_type === itype).length;
                return (
                  <button
                    key={itype}
                    onClick={() => setIncidentType(incidentType === itype ? null : itype)}
                    className={`w-full flex items-center justify-between p-2 rounded hover:bg-slate-800/50 transition-colors ${incidentType === itype ? 'bg-slate-800/80' : ''}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
                      <span className="text-xs text-slate-400">{itype.replace(/_/g, ' ')}</span>
                    </div>
                    <span className="text-xs font-bold text-white">{count}</span>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Incidents Table + Active Permits */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Incidents */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Recent Incidents</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Date</th>
                    <th className="text-center py-2 px-3 font-medium">Type</th>
                    <th className="text-left py-2 px-3 font-medium">Description</th>
                    <th className="text-left py-2 px-3 font-medium">Area</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {incidentList.slice(0, 20).map((inc: any) => (
                    <tr key={inc.incident_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-3 text-slate-400">{inc.incident_date}</td>
                      <td className="py-2 px-3 text-center">
                        <span className="font-semibold text-xs" style={{ color: INCIDENT_COLORS[inc.incident_type] || '#94a3b8' }}>
                          {inc.incident_type}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-slate-300 max-w-[180px] truncate" title={inc.description}>{inc.description}</td>
                      <td className="py-2 px-3 text-slate-400">{inc.area_code || '—'}</td>
                      <td className="py-2 px-3 text-center">
                        <Badge variant={inc.status === 'CLOSED' ? 'success' : 'warning'}>{inc.status}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>

        {/* Active Permits */}
        <Card>
          <CardHeader><CardTitle className="text-sm">Active Permits</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-72 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Permit #</th>
                    <th className="text-center py-2 px-3 font-medium">Type</th>
                    <th className="text-left py-2 px-3 font-medium">Work Description</th>
                    <th className="text-left py-2 px-3 font-medium">Area</th>
                    <th className="text-center py-2 px-3 font-medium">Expiry</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {permitList.slice(0, 20).map((p: any) => (
                    <tr key={p.permit_id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 ${p.is_expired ? 'bg-red-500/5' : ''}`}>
                      <td className="py-2 px-3 font-mono text-slate-300">{p.permit_number}</td>
                      <td className="py-2 px-3 text-center">
                        <span className="text-slate-400">{p.permit_type?.replace(/_/g, ' ')}</span>
                      </td>
                      <td className="py-2 px-3 text-slate-300 max-w-[150px] truncate" title={p.work_description}>{p.work_description}</td>
                      <td className="py-2 px-3 text-slate-400">{p.area_code || '—'}</td>
                      <td className="py-2 px-3 text-center">
                        {p.is_expired
                          ? <Badge variant="destructive">Expired</Badge>
                          : p.is_expiring_soon
                          ? <Badge variant="warning">{p.days_to_expiry}d left</Badge>
                          : <span className="text-slate-400">{p.expiry_date}</span>
                        }
                      </td>
                      <td className="py-2 px-3 text-center">
                        <Badge variant={p.status === 'ISSUED' ? 'success' : 'default'}>{p.status}</Badge>
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
