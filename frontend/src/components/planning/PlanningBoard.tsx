import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { Button } from '../ui/Button';
import { apiClient } from '../../lib/api-client';
import { Calendar, Clock, Flag, AlertTriangle, CheckCircle, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react';

const PERIOD_TYPES = [
  { value: 'WEEKLY', label: 'Weekly', count: 16 },
  { value: 'BI_WEEKLY', label: 'Bi-Weekly', count: 8 },
  { value: 'MONTHLY', label: 'Monthly', count: 4 },
  { value: 'BI_MONTHLY', label: 'Bi-Monthly', count: 2 },
  { value: 'FOUR_MONTH', label: '4-Month', count: 1 },
];

const STATUS_COLORS: Record<string, string> = {
  ON_TRACK: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  AT_RISK: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  DELAYED: 'bg-red-500/10 text-red-400 border-red-500/30',
  COMPLETED: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
};

export function PlanningBoard({ projectId }: { projectId: string }) {
  const [periodType, setPeriodType] = useState('WEEKLY');
  const [expandedPeriods, setExpandedPeriods] = useState<Set<string>>(new Set());

  const queryClient = useQueryClient();

  const { data: boardData, isLoading } = useQuery({
    queryKey: ['planning-board', projectId, periodType],
    queryFn: () => apiClient.get(`/api/planning/board/${projectId}?period_type=${periodType}`),
    refetchInterval: 30000,
  });

  const handleGenerate = async () => {
    await apiClient.post(`/api/planning/generate/${projectId}`);
    queryClient.invalidateQueries({ queryKey: ['planning-board'] });
    queryClient.invalidateQueries({ queryKey: ['planning-periods'] });
  };

  const togglePeriod = (id: string) => {
    setExpandedPeriods(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const periods = boardData?.data?.periods || [];
  const items = boardData?.data?.items || [];
  const summary = boardData?.data?.summary || {};

  const itemsByPeriod = items.reduce((acc: Record<string, any[]>, item: any) => {
    const pid = item.period_id;
    if (!acc[pid]) acc[pid] = [];
    acc[pid].push(item);
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <Calendar className="h-5 w-5 text-blue-400" />
          <h3 className="text-lg font-semibold text-white">Multi-Level Planning Board</h3>
        </div>
        <Button onClick={handleGenerate} className="flex items-center gap-2 text-xs">
          <RefreshCw className="h-3.5 w-3.5" />
          Generate Plans
        </Button>
      </div>

      {/* Period Type Tabs */}
      <div className="flex gap-1 bg-slate-900 rounded-lg p-1 w-fit">
        {PERIOD_TYPES.map(pt => (
          <button
            key={pt.value}
            onClick={() => setPeriodType(pt.value)}
            className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              periodType === pt.value
                ? 'bg-primary/20 text-white shadow-sm'
                : 'text-slate-400 hover:text-white hover:bg-slate-800'
            }`}
          >
            {pt.label} <span className="text-slate-600">({pt.count})</span>
          </button>
        ))}
      </div>

      {/* Summary KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Total Items</p>
            <p className="text-xl font-bold">{summary.total_items || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Milestones</p>
            <p className="text-xl font-bold text-purple-400">{summary.milestones || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">On Track</p>
            <p className="text-xl font-bold text-emerald-400">{summary.on_track || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">At Risk</p>
            <p className="text-xl font-bold text-amber-400">{summary.at_risk || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Delayed</p>
            <p className="text-xl font-bold text-red-400">{summary.delayed || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Period List with Items */}
      {isLoading ? (
        <div className="text-center py-10 text-slate-500">Loading planning data...</div>
      ) : periods.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center">
            <Calendar className="h-10 w-10 text-slate-600 mx-auto mb-3" />
            <p className="text-slate-400">No planning periods found</p>
            <p className="text-xs text-slate-600 mt-1">Click "Generate Plans" to auto-create planning periods</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-2">
          {periods.map((period: any) => {
            const periodItems = itemsByPeriod[period.period_id] || [];
            const isExpanded = expandedPeriods.has(period.period_id);
            const completedCount = periodItems.filter((i: any) => i.status === 'COMPLETED').length;
            const delayedCount = periodItems.filter((i: any) => i.status === 'DELAYED').length;
            const atRiskCount = periodItems.filter((i: any) => i.status === 'AT_RISK').length;

            return (
              <Card key={period.period_id} className={period.is_locked ? 'border-l-4 border-l-slate-600' : ''}>
                <button
                  onClick={() => togglePeriod(period.period_id)}
                  className="w-full text-left focus:outline-none"
                >
                  <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        {isExpanded
                          ? <ChevronDown className="h-4 w-4 text-slate-400" />
                          : <ChevronRight className="h-4 w-4 text-slate-400" />
                        }
                        <div>
                          <p className="text-sm font-semibold text-white">
                            {period.period_label || `${period.period_start} — ${period.period_end}`}
                          </p>
                          <p className="text-[10px] text-slate-500">
                            {period.period_start} to {period.period_end}
                            {period.is_locked && <span className="ml-2 text-slate-500">🔒 Locked</span>}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-slate-400">{period.item_count} items</span>
                        {completedCount > 0 && <Badge variant="success">{completedCount} done</Badge>}
                        {atRiskCount > 0 && <Badge variant="warning">{atRiskCount} at risk</Badge>}
                        {delayedCount > 0 && <Badge variant="destructive">{delayedCount} delayed</Badge>}
                      </div>
                    </div>
                  </CardContent>
                </button>

                {/* Expanded Items */}
                {isExpanded && periodItems.length > 0 && (
                  <div className="border-t border-slate-800">
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-slate-500 border-b border-slate-800">
                            <th className="text-left py-2 px-4 font-medium">Activity</th>
                            <th className="text-center py-2 px-3 font-medium">Work Scope</th>
                            <th className="text-center py-2 px-3 font-medium">Critical</th>
                            <th className="text-center py-2 px-3 font-medium">Planned %</th>
                            <th className="text-center py-2 px-3 font-medium">Actual %</th>
                            <th className="text-center py-2 px-3 font-medium">Current</th>
                            <th className="text-center py-2 px-3 font-medium">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {periodItems.map((item: any) => (
                            <tr key={item.plan_item_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                              <td className="py-2 px-4">
                                <div className="flex items-center gap-2">
                                  {item.milestone_flag && <Flag className="h-3 w-3 text-purple-400" />}
                                  <span className="text-slate-300">{item.activity_code}</span>
                                  <span className="text-slate-500">{item.activity_name}</span>
                                </div>
                              </td>
                              <td className="text-center py-2 px-3 text-slate-400">{item.work_scope_category || '—'}</td>
                              <td className="text-center py-2 px-3">
                                {item.is_critical ? <AlertTriangle className="h-3.5 w-3.5 text-red-400 mx-auto" /> : '—'}
                              </td>
                              <td className="text-center py-2 px-3 font-mono text-slate-300">{item.planned_weight_pct || 0}%</td>
                              <td className="text-center py-2 px-3 font-mono text-slate-300">{item.actual_weight_pct || 0}%</td>
                              <td className="text-center py-2 px-3">
                                <div className="flex items-center gap-1 justify-center">
                                  <Progress value={item.current_progress || 0} className="w-12 h-1.5" />
                                  <span className="font-mono text-slate-400 text-[10px]">{item.current_progress || 0}%</span>
                                </div>
                              </td>
                              <td className="text-center py-2 px-3">
                                <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium border ${STATUS_COLORS[item.status] || 'text-slate-400 border-slate-700'}`}>
                                  {item.status?.replace('_', ' ') || '—'}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                {isExpanded && periodItems.length === 0 && (
                  <div className="border-t border-slate-800 py-4 text-center text-xs text-slate-600">
                    No items in this period
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
