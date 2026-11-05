import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { Button } from '../ui/Button';
import { apiClient } from '../../lib/api-client';
import { DoorOpen, CheckCircle, XCircle, AlertTriangle, ArrowRight, Brain, Shield, Clock } from 'lucide-react';

const GATE_STATUS_COLORS: Record<string, string> = {
  PENDING: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
  IN_REVIEW: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
  APPROVED: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  REJECTED: 'bg-red-500/10 text-red-400 border-red-500/30',
  CONDITIONAL: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
};

export function StageGateControl({ projectId }: { projectId: string }) {
  const [selectedGateId, setSelectedGateId] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: gates } = useQuery({
    queryKey: ['stage-gates', projectId],
    queryFn: () => apiClient.get(`/api/stagegate/${projectId}`),
    refetchInterval: 30000,
  });

  const { data: gateDetail } = useQuery({
    queryKey: ['stage-gate-detail', projectId, selectedGateId],
    queryFn: () => apiClient.get(`/api/stagegate/${projectId}/${selectedGateId}`),
    enabled: !!selectedGateId,
  });

  const gateList = gates?.data || [];
  const detail = gateDetail?.data || {};

  const runAssessment = async (gateId: string) => {
    await apiClient.post(`/api/stagegate/assess/${projectId}/${gateId}`);
    queryClient.invalidateQueries({ queryKey: ['stage-gates'] });
    queryClient.invalidateQueries({ queryKey: ['stage-gate-detail'] });
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <DoorOpen className="h-5 w-5 text-indigo-400" />
        <h3 className="text-lg font-semibold text-white">Stage Gate Control</h3>
      </div>

      {/* Gate Sequence */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2">
        {gateList.map((gate: any, idx: number) => (
          <div key={gate.gate_id} className="flex items-center gap-2 shrink-0">
            <button
              onClick={() => setSelectedGateId(gate.gate_id)}
              className={`flex flex-col items-center p-3 rounded-lg border-2 min-w-[160px] transition-all ${
                selectedGateId === gate.gate_id
                  ? 'border-primary bg-primary/5'
                  : gate.status === 'APPROVED'
                  ? 'border-emerald-500/50 bg-emerald-500/5'
                  : gate.status === 'REJECTED'
                  ? 'border-red-500/50 bg-red-500/5'
                  : 'border-slate-700 hover:border-slate-600'
              }`}
            >
              <span className="text-[10px] text-slate-500 mb-1">Gate {gate.gate_sequence}</span>
              <span className="text-xs font-semibold text-white">{gate.gate_name}</span>
              <span className="text-[10px] text-slate-500 mt-1">
                {gate.from_phase} → {gate.to_phase}
              </span>
              <div className="mt-2 flex items-center gap-1">
                <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-medium border ${GATE_STATUS_COLORS[gate.status] || ''}`}>
                  {gate.status}
                </span>
              </div>
              {gate.ai_readiness_score != null && (
                <div className="mt-2 flex items-center gap-1">
                  <Brain className="h-3 w-3 text-purple-400" />
                  <span className="text-xs font-bold text-purple-400">{gate.ai_readiness_score}/10</span>
                </div>
              )}
              {gate.status === 'PENDING' && (
                <Button onClick={(e: any) => { e.stopPropagation(); runAssessment(gate.gate_id); }} className="mt-2 text-[10px] px-2 py-1">
                  <Brain className="h-3 w-3 mr-1" /> Assess
                </Button>
              )}
            </button>
            {idx < gateList.length - 1 && (
              <ArrowRight className="h-5 w-5 text-slate-600 shrink-0" />
            )}
          </div>
        ))}
      </div>

      {/* Gate Detail */}
      {selectedGateId && detail.gate && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Left: Gate Info */}
          <Card>
            <CardHeader><CardTitle className="text-sm">Gate Detail</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-3">
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Gate Name</p>
                  <p className="text-sm font-semibold text-white">{detail.gate.gate_name}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Transition</p>
                  <p className="text-sm text-white">{detail.gate.from_phase} → {detail.gate.to_phase}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Planned Date</p>
                  <p className="text-sm text-white">{detail.gate.planned_date || 'Not set'}</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Status</p>
                  <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium border ${GATE_STATUS_COLORS[detail.gate.status] || ''}`}>
                    {detail.gate.status}
                  </span>
                </div>

                {/* AI Score */}
                <div className="p-3 rounded-lg bg-slate-800/50 border border-slate-700">
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="h-4 w-4 text-purple-400" />
                    <span className="text-sm font-semibold text-white">AI Readiness Score</span>
                  </div>
                  <div className="flex items-end gap-2">
                    <span className={`text-3xl font-bold ${
                      (detail.ai_readiness_score || 0) >= 8 ? 'text-emerald-400'
                      : (detail.ai_readiness_score || 0) >= 6 ? 'text-amber-400'
                      : 'text-red-400'
                    }`}>
                      {detail.ai_readiness_score || '—'}
                    </span>
                    <span className="text-xs text-slate-500 mb-1">/ 10</span>
                  </div>
                  <Progress value={(detail.ai_readiness_score || 0) * 10} className="h-1.5 mt-2" />
                </div>

                {/* Checklist Stats */}
                {detail.checklist_stats && (
                  <div className="flex gap-2 text-xs">
                    <span className="text-slate-400">{detail.checklist_stats.total} checklist items</span>
                    <span className="text-emerald-400">{detail.checklist_stats.completed} complete</span>
                    <span className="text-white font-bold">{detail.checklist_stats.pct}%</span>
                  </div>
                )}

                <Button
                  onClick={() => runAssessment(selectedGateId)}
                  className="w-full text-xs"
                >
                  <Brain className="h-3.5 w-3.5 mr-1.5" />
                  Re-run AI Assessment
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Right: Checklist Items */}
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-sm">Gate Checklist ({detail.checklist?.length || 0} items)</CardTitle>
            </CardHeader>
            <CardContent>
              {detail.checklist?.length > 0 ? (
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {detail.checklist.map((ci: any) => (
                    <div key={ci.checklist_item_id} className={`p-2.5 rounded-lg border ${ci.is_complete ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-slate-800 bg-slate-800/30'}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-start gap-2">
                          {ci.is_complete
                            ? <CheckCircle className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0" />
                            : <div className="w-4 h-4 rounded-full border border-slate-600 mt-0.5 shrink-0" />
                          }
                          <div>
                            <div className="flex items-center gap-2 mb-0.5">
                              <span className="text-[10px] font-mono text-slate-500">#{ci.item_number}</span>
                              {ci.category && (
                                <span className="text-[10px] text-slate-500">{ci.category}</span>
                              )}
                            </div>
                            <p className="text-xs text-slate-300">{ci.description}</p>
                            {ci.verification_method && (
                              <p className="text-[10px] text-slate-500 mt-0.5">Method: {ci.verification_method}</p>
                            )}
                            {ci.verified_by && (
                              <p className="text-[10px] text-slate-500">
                                Verified by {ci.verified_by} {ci.verified_date?.slice(0, 10)}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-slate-500">
                  <p className="text-xs">No checklist items defined for this gate</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
