import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { apiClient } from '../../lib/api-client';
import { MessageSquare, ArrowRight, Clock, AlertTriangle, Filter } from 'lucide-react';

const STAGE_COLORS: Record<string, string> = {
  ENGINEERING: '#3b82f6',
  PROCUREMENT: '#f59e0b',
  CONSTRUCTION: '#10b981',
  SYSTEM_COMPLETION: '#8b5cf6',
  COMMISSIONING: '#06b6d4',
};

const FEEDBACK_TYPE_LABELS: Record<string, string> = {
  DESIGN_CHANGE: 'Design Change',
  MATERIAL_SUBSTITUTION: 'Material Substitution',
  SCHEDULE_ADJUSTMENT: 'Schedule Adjustment',
  SCOPE_VARIATION: 'Scope Variation',
  QUALITY_ISSUE: 'Quality Issue',
  SAFETY_CONCERN: 'Safety Concern',
  TECHNICAL_QUERY: 'Technical Query',
};

export function FeedbackLoopDashboard({ projectId }: { projectId: string }) {
  const [actedFilter, setActedFilter] = useState<boolean | null>(null);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);

  const { data: feedback, isLoading } = useQuery({
    queryKey: ['feedback', projectId, actedFilter, sourceFilter],
    queryFn: () => {
      let url = `/api/feedback/${projectId}`;
      const params = new URLSearchParams();
      if (actedFilter !== null) params.set('is_actioned', String(actedFilter));
      if (sourceFilter) params.set('source_stage', sourceFilter);
      const qs = params.toString();
      return apiClient.get(qs ? `${url}?${qs}` : url);
    },
    refetchInterval: 30000,
  });

  const { data: summary } = useQuery({
    queryKey: ['feedback-summary', projectId],
    queryFn: () => apiClient.get(`/api/feedback/summary/${projectId}`),
    refetchInterval: 30000,
  });

  const { data: stale } = useQuery({
    queryKey: ['feedback-stale', projectId],
    queryFn: () => apiClient.get(`/api/feedback/stale/${projectId}?days_stale=14`),
    refetchInterval: 30000,
  });

  const items = feedback?.data || [];
  const sum = summary?.data || {};
  const staleItems = stale?.data || [];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <MessageSquare className="h-5 w-5 text-cyan-400" />
        <h3 className="text-lg font-semibold text-white">Feedback Loop</h3>
      </div>

      {/* Stale Feedback Alert */}
      {staleItems.length > 0 && (
        <Card className="border-l-4 border-l-red-500">
          <CardContent className="py-3">
            <div className="flex items-center gap-2 text-sm">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <span className="text-red-400 font-semibold">{staleItems.length} feedback items unactioned for 14+ days</span>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Summary: By Direction */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {sum.by_direction && (
          <Card>
            <CardHeader><CardTitle className="text-sm">By Direction</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(sum.by_direction || []).slice(0, 8).map((d: any) => (
                  <div key={d.direction} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">{d.direction.split('→')[0]}</span>
                      <ArrowRight className="h-3 w-3 text-slate-600" />
                      <span className="text-slate-400">{d.direction.split('→')[1]}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{d.count}</span>
                      <span className={d.actioned === d.count ? 'text-emerald-400' : 'text-amber-400'}>
                        {d.actioned}/{d.count} actioned
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* By Type */}
        {sum.by_type && (
          <Card>
            <CardHeader><CardTitle className="text-sm">By Type</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(sum.by_type || []).map((t: any) => (
                  <div key={t.feedback_type} className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">{FEEDBACK_TYPE_LABELS[t.feedback_type] || t.feedback_type}</span>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{t.count}</span>
                      <span className={t.actioned === t.count ? 'text-emerald-400' : 'text-amber-400'}>
                        {t.actioned}/{t.count}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* Feedback Items List */}
      {isLoading ? (
        <div className="text-center py-10 text-slate-500">Loading feedback...</div>
      ) : (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Direction</th>
                    <th className="text-center py-2 px-3 font-medium">Type</th>
                    <th className="text-left py-2 px-3 font-medium">Description</th>
                    <th className="text-center py-2 px-3 font-medium">Impact</th>
                    <th className="text-center py-2 px-3 font-medium">Created</th>
                    <th className="text-center py-2 px-3 font-medium">Actioned</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((f: any) => (
                    <tr key={f.feedback_id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 ${!f.is_actioned ? 'bg-amber-500/3' : ''}`}>
                      <td className="py-2 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-semibold" style={{ color: STAGE_COLORS[f.source_stage] || '#94a3b8' }}>
                            {f.source_stage?.replace(/_/g, ' ')}
                          </span>
                          <ArrowRight className="h-3 w-3 text-slate-600" />
                          <span className="text-xs font-semibold" style={{ color: STAGE_COLORS[f.target_stage] || '#94a3b8' }}>
                            {f.target_stage?.replace(/_/g, ' ')}
                          </span>
                        </div>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className="text-slate-400">{FEEDBACK_TYPE_LABELS[f.feedback_type] || f.feedback_type}</span>
                      </td>
                      <td className="py-2 px-3 text-slate-300 max-w-[250px] truncate" title={f.description}>{f.description}</td>
                      <td className="py-2 px-3 text-center">
                        <Badge variant={f.impact_level === 'HIGH' ? 'destructive' : f.impact_level === 'MEDIUM' ? 'warning' : 'default'}>
                          {f.impact_level}
                        </Badge>
                      </td>
                      <td className="py-2 px-3 text-center text-slate-400">{f.created_at?.slice(0, 10)}</td>
                      <td className="py-2 px-3 text-center">
                        {f.is_actioned ? (
                          <Badge variant="success">Yes</Badge>
                        ) : (
                          <Badge variant="warning">Pending</Badge>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
