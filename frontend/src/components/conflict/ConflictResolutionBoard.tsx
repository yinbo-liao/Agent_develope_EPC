import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { apiClient } from '../../lib/api-client';
import { AlertTriangle, CheckCircle, Clock, Filter, Brain, ArrowRight } from 'lucide-react';
import { TableSkeleton } from '../ui/LoadingSkeleton';

const CONFLICT_TYPE_LABELS: Record<string, string> = {
  SCHEDULE_CLASH: 'Schedule Clash',
  RESOURCE_CONFLICT: 'Resource Conflict',
  DESIGN_CLASH: 'Design Clash',
  INTERFACE_GAP: 'Interface Gap',
  SCOPE_CHANGE: 'Scope Change',
  MATERIAL_DELAY: 'Material Delay',
  MANPOWER_SHORTAGE: 'Manpower Shortage',
  VENDOR_ISSUE: 'Vendor Issue',
  SAFETY_RISK: 'Safety Risk',
};

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-red-600/20 text-red-400 border-red-600/40',
  HIGH: 'bg-red-500/10 text-red-400 border-red-500/30',
  MEDIUM: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  LOW: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

const STATUS_COLORS: Record<string, string> = {
  DETECTED: 'bg-red-500/10 text-red-400',
  ACKNOWLEDGED: 'bg-amber-500/10 text-amber-400',
  IN_RESOLUTION: 'bg-blue-500/10 text-blue-400',
  RESOLVED: 'bg-emerald-500/10 text-emerald-400',
  CLOSED: 'bg-slate-500/10 text-slate-400',
};

export function ConflictResolutionBoard({ projectId }: { projectId: string }) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [selectedConflictId, setSelectedConflictId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: conflicts, isLoading } = useQuery({
    queryKey: ['conflicts', projectId, statusFilter],
    queryFn: () => {
      let url = `/api/conflicts/${projectId}`;
      if (statusFilter) url += `?status=${statusFilter}`;
      return apiClient.get(url);
    },
    refetchInterval: 30000,
  });

  const { data: summary } = useQuery({
    queryKey: ['conflict-summary', projectId],
    queryFn: () => apiClient.get(`/api/conflicts/summary/${projectId}`),
    refetchInterval: 30000,
  });

  const conflictList = conflicts?.data || [];
  const sum = summary?.data || {};

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-orange-400" />
        <h3 className="text-lg font-semibold text-white">Conflict Resolution Board</h3>
      </div>

      {/* Summary by Severity + AI detection stats */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(sum.by_severity || []).map((s: any) => (
          <Card key={s.severity}>
            <CardContent className="py-3 text-center">
              <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border mb-1 ${SEVERITY_COLORS[s.severity] || ''}`}>
                {s.severity}
              </span>
              <p className="text-xl font-bold">{s.count || 0}</p>
              <p className="text-[10px] text-slate-500">{s.open || 0} open</p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* AI Detection Stats */}
      {sum.ai_detection_stats && sum.ai_detection_stats.length > 0 && (
        <Card className="border-l-4 border-l-purple-500">
          <CardContent className="py-3">
            <div className="flex items-center gap-2 mb-1">
              <Brain className="h-4 w-4 text-purple-400" />
              <span className="text-sm font-semibold text-white">AI Detection Performance</span>
            </div>
            <div className="flex gap-4 text-xs">
              {sum.ai_detection_stats.map((s: any) => (
                <div key={String(s.detected_by_agent)}>
                  <span className="text-slate-500">{s.detected_by_agent ? 'AI-Detected' : 'Manual'}: </span>
                  <span className="text-white font-semibold">{s.count}</span>
                  {s.avg_confidence && <span className="text-slate-500 ml-1">(avg {s.avg_confidence} confidence)</span>}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Conflict List */}
      {isLoading ? (
        <TableSkeleton rows={5} cols={4} />
      ) : (
        <div className="space-y-2">
          {conflictList.map((c: any) => (
            <Card key={c.conflict_id} className={`${c.severity === 'CRITICAL' ? 'border-l-4 border-l-red-500' : ''} ${c.detected_by_agent ? 'border-r-4 border-r-purple-500/30' : ''}`}>
              <CardContent className="py-3">
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    {/* Header Row */}
                    <div className="flex items-center gap-2 flex-wrap mb-1">
                      <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-bold border ${SEVERITY_COLORS[c.severity] || ''}`}>
                        {c.severity}
                      </span>
                      <span className="text-xs text-slate-400">
                        {CONFLICT_TYPE_LABELS[c.conflict_type] || c.conflict_type}
                      </span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[c.status] || ''}`}>
                        {c.status?.replace(/_/g, ' ')}
                      </span>
                      {c.detected_by_agent && (
                        <span className="flex items-center gap-0.5 text-[10px] text-purple-400">
                          <Brain className="h-3 w-3" /> AI
                          {c.ai_confidence && <span>({Math.round(c.ai_confidence * 100)}%)</span>}
                        </span>
                      )}
                    </div>

                    {/* Title & Description */}
                    {c.title && <p className="text-sm font-semibold text-white">{c.title}</p>}
                    <p className="text-xs text-slate-300 mt-0.5">{c.description}</p>

                    {/* AI Recommendation */}
                    {c.ai_recommendation && (
                      <div className="mt-2 p-2 rounded bg-purple-500/5 border border-purple-500/20">
                        <p className="text-[10px] text-purple-400 font-medium mb-0.5">AI Recommendation:</p>
                        <p className="text-xs text-slate-300">{c.ai_recommendation}</p>
                      </div>
                    )}

                    {/* Meta row */}
                    <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-500">
                      {c.source_entity_type && (
                        <span>Source: {c.source_entity_type}</span>
                      )}
                      {c.open_actions !== undefined && c.open_actions > 0 && (
                        <span className="text-amber-400">{c.open_actions} open actions</span>
                      )}
                      <span>Created: {c.created_at?.slice(0, 10)}</span>
                    </div>

                    {/* Resolution Notes */}
                    {c.resolution_notes && (
                      <div className="mt-2 p-2 rounded bg-slate-800/50 border border-slate-700">
                        <p className="text-[10px] text-slate-400">Resolution: {c.resolution_notes}</p>
                        {c.resolved_by && <p className="text-[10px] text-slate-500">Resolved by: {c.resolved_by}</p>}
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
