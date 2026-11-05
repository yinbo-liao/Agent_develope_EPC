import { useQuery } from '@tanstack/react-query';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Progress } from '../ui/Progress';
import { Badge } from '../ui/Badge';
import { AlertTriangle } from 'lucide-react';
import { apiClient } from '../../lib/api-client';

export function WeeklyPlanner({ projectId, weekStart }: { projectId: string; weekStart: Date }) {
  const ws = weekStart.toISOString().split('T')[0];

  const { data: tasksData } = useQuery({
    queryKey: ['weekly-planning', projectId, ws],
    queryFn: () => apiClient.get(`/api/construction/weekly-planning/${projectId}?week_start=${ws}`),
  });
  const { data: shortagesData } = useQuery({
    queryKey: ['shortages', projectId],
    queryFn: () => apiClient.get(`/api/construction/resource-shortages/${projectId}`),
    refetchInterval: 15000,
  });
  const tasks = tasksData?.data || [];
  const shortages = shortagesData?.data || [];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Weekly Task Completion (Week of {weekStart.toLocaleDateString()})</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          {tasks.map((task: any) => {
            const pct = task.planned_completion_percent > 0 ? (task.actual_completion_percent / task.planned_completion_percent) * 100 : 0;
            return (
              <div key={task.task_id} className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="font-medium">{task.planned_status || task.activity_name}</span>
                  <span className="text-slate-400">{task.actual_completion_percent}% / {task.planned_completion_percent}%</span>
                </div>
                <Progress value={pct} />
                {task.delay_reason && (
                  <div className="flex items-center gap-1 text-red-400 text-xs mt-1">
                    <AlertTriangle className="h-3 w-3" /> {task.delay_reason}
                  </div>
                )}
              </div>
            );
          })}
          {tasks.length === 0 && <p className="text-center text-slate-500 py-3">No tasks planned for this week</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Active Resource Shortages</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {shortages.map((s: any) => (
            <div key={s.shortage_id} className="flex items-start gap-3 p-3 bg-red-950/30 border border-red-900/50 rounded-lg">
              <AlertTriangle className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{s.resource_name}</span>
                  <Badge variant="destructive">{s.shortage_type}</Badge>
                </div>
                <p className="text-sm text-slate-300">Shortfall: {s.shortfall} units (Required: {s.required_quantity}, Available: {s.available_quantity})</p>
                {s.impact_description && <p className="text-xs text-slate-400 mt-1">{s.impact_description}</p>}
              </div>
            </div>
          ))}
          {shortages.length === 0 && <p className="text-center text-emerald-400 py-3">No open resource shortages</p>}
        </CardContent>
      </Card>
    </div>
  );
}
