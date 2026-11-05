import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Progress } from '../ui/Progress';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { Printer, TrendingUp, CheckCircle, AlertTriangle } from 'lucide-react';
import { apiClient } from '../../lib/api-client';

export function AccountabilityReport({ projectId, weekEnding }: { projectId: string; weekEnding: Date }) {
  const we = weekEnding.toISOString().split('T')[0];
  const { data, isLoading } = useQuery({
    queryKey: ['accountability', projectId, we],
    queryFn: () => apiClient.get(`/api/reports/accountability/${projectId}?week_end=${we}`),
  });
  const report = data?.data;

  if (isLoading) return <div className="text-slate-400 p-6">Generating accountability report...</div>;
  if (!report) return null;

  const taskPct = report.task_summary.planned_pct > 0 ? (report.task_summary.actual_pct / report.task_summary.planned_pct) * 100 : 0;

  return (
    <div className="space-y-6">
      <Card className="border-t-4 border-t-primary-accent print:shadow-none">
        <CardHeader>
          <CardTitle>Accountability Report - Week Ending {weekEnding.toDateString()}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Task Achievement */}
          <div>
            <div className="flex items-center gap-2 mb-2"><CheckCircle className="h-4 w-4 text-emerald-400" /><h4 className="font-semibold">Weekly Task Achievement</h4></div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-slate-900/60 p-3 rounded-lg"><span className="text-slate-400">Tasks Completed</span><p className="text-xl font-bold text-white">{report.task_summary.completed} / {report.task_summary.total}</p></div>
              <div className="bg-slate-900/60 p-3 rounded-lg"><span className="text-slate-400">Progress</span><p className="text-xl font-bold text-white">{report.task_summary.actual_pct?.toFixed(1)}%</p></div>
            </div>
            <Progress value={taskPct} className="mt-3" />
            <p className="text-xs text-slate-500 mt-1">Planned: {report.task_summary.planned_pct?.toFixed(1)}% | Actual: {report.task_summary.actual_pct?.toFixed(1)}%</p>
          </div>

          {/* NDT Achievement */}
          <div>
            <div className="flex items-center gap-2 mb-2"><TrendingUp className="h-4 w-4 text-blue-400" /><h4 className="font-semibold">NDT Achievement</h4></div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="bg-slate-900/60 p-3 rounded-lg"><span className="text-slate-400">Requests Completed</span><p className="text-xl font-bold text-white">{report.ndt_achievement.completed} / {report.ndt_achievement.total_requests}</p></div>
              <div className="bg-slate-900/60 p-3 rounded-lg"><span className="text-slate-400">Average Completion</span><p className="text-xl font-bold text-white">{report.ndt_achievement.avg_complete_pct?.toFixed(1)}%</p></div>
            </div>
          </div>

          {/* Manpower Productivity */}
          <div>
            <h4 className="font-semibold mb-2">Manpower Productivity Trend</h4>
            <div className="h-48">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={report.manpower_productivity}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                  <XAxis dataKey="report_date" stroke="#94a3b8" fontSize={11} />
                  <YAxis stroke="#94a3b8" fontSize={11} domain={[0, 150]} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '8px', color: '#e2e8f0' }} />
                  <Line type="monotone" dataKey="productivity_pct" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} name="Productivity %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Top Shortages */}
          <div>
            <div className="flex items-center gap-2 mb-2"><AlertTriangle className="h-4 w-4 text-amber-400" /><h4 className="font-semibold">Top Resource Shortages</h4></div>
            <div className="space-y-2">
              {report.top_shortages?.map((s: any) => (
                <div key={s.resource_name} className="flex items-center justify-between bg-slate-900/60 p-2.5 rounded-lg">
                  <span>{s.resource_name}</span>
                  <Badge variant="destructive">-{s.shortfall}</Badge>
                </div>
              ))}
              {(!report.top_shortages || report.top_shortages.length === 0) && <p className="text-sm text-emerald-400">No active shortages</p>}
            </div>
          </div>

          <Button onClick={() => window.print()} className="w-full flex items-center gap-2">
            <Printer className="h-4 w-4" /> Print Report
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
