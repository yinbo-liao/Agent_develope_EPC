import { useQuery, useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Progress } from '../ui/Progress';
import { Badge } from '../ui/Badge';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { apiClient } from '../../lib/api-client';
import { FileText, X, Save } from 'lucide-react';

const COLORS = ['#3b82f6', '#8b5cf6', '#06b6d4', '#10b981'];
const NDT_METHODS = ['RT', 'UT', 'MT', 'PT'];

const NDT_RULES: Record<string, Record<string, string>> = {
  'pipe-class-I': { RT: '100%', UT: '-', MT: '100%', PT: '100%' },
  'pipe-class-II': { RT: '10%', UT: '-', MT: '10%', PT: '10%' },
  'pipe-class-III': { RT: '5%', UT: '5%', MT: '5%', PT: '5%' },
  'Str-Pri-I': { RT: '-', UT: '50% (CS)', MT: '50% (CS)', PT: 'SS only' },
  'Str-Pri-II': { RT: '-', UT: '10% (CS)', MT: '10% (CS)', PT: 'SS only' },
  'Str-Pri-III': { RT: '5%', UT: '5%', MT: '5%', PT: '5%' },
};

function calcOutstanding(rfiTotal: number, ndtDone: number): string {
  const diff = rfiTotal - ndtDone;
  if (diff <= 0) return 'No outstanding';
  return `NDT outstanding ${diff.toLocaleString()} mm`;
}

const NDT_DISCIPLINES = [
  { name: 'STRUCTURAL', color: '#3b82f6' },
  { name: 'PIPING', color: '#8b5cf6' },
];

export function NDTProgressChart({ projectId }: { projectId: string }) {
  const [selectedDiscipline, setSelectedDiscipline] = useState<string>('STRUCTURAL');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [selectedDrawingNumber, setSelectedDrawingNumber] = useState<string | null>(null);
  const [editMap, setEditMap] = useState<Record<string, { team: number; dailyDone: number; remarks: string }>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['ndt-summary', projectId],
    queryFn: () => apiClient.get(`/api/inspection/ndt-summary/${projectId}`),
    refetchInterval: 10000,
  });

  const { data: progressData } = useQuery({
    queryKey: ['ndt-progress-table', projectId],
    queryFn: () => apiClient.get(`/api/inspection/ndt-progress-table/${projectId}`),
    refetchInterval: 10000,
  });
  const progressRows: any[] = progressData?.data || [];

  const { data: registerData, isLoading: registerLoading } = useQuery({
    queryKey: ['ndt-drawing-register', projectId],
    queryFn: () => apiClient.get(`/api/inspection/ndt-drawing-register/${projectId}`),
    refetchInterval: 10000,
  });
  const allRegisterDrawings: any[] = registerData?.data || [];
  const disciplineRegisterDrawings = allRegisterDrawings.filter(
    (d: any) => d.discipline_name === selectedDiscipline
  );

  const { data: ndtDrawingData } = useQuery({
    queryKey: ['ndt-drawing-summary', projectId, selectedDrawingId],
    queryFn: () => apiClient.get(`/api/inspection/ndt-drawing-summary/${projectId}/${selectedDrawingId}`),
    enabled: !!selectedDrawingId,
    refetchInterval: 10000,
  });
  const ndtDrawingSummary: any[] = ndtDrawingData?.data || [];

  const handleStartEdit = (row: any) => {
    const key = `${row.log_id}`;
    setEditMap((prev) => ({ ...prev, [key]: { team: row.team_deployed || 0, dailyDone: row.daily_length_done_mm || 0, remarks: row.remarks || '' } }));
  };

  const handleSave = async (row: any) => {
    const key = `${row.log_id}`;
    setSaving((prev) => ({ ...prev, [key]: true }));
    try {
      await apiClient.post('/api/inspection/ndt-daily-log', {
        log_id: row.log_id, project_id: projectId, log_date: row.log_date,
        discipline_name: row.discipline_name, ndt_method: row.ndt_method,
        rfi_total_length_mm: row.rfi_total_length_mm,
        ndt_complete_length_mm: (row.ndt_complete_length_mm || 0) + (editMap[key]?.dailyDone || 0),
        daily_length_done_mm: editMap[key]?.dailyDone || 0,
        team_deployed: editMap[key]?.team || 0,
        previous_status: row.previous_status,
        remarks: editMap[key]?.remarks || '',
        updated_by: 'QA/NDT Engineer',
      });
      queryClient.invalidateQueries({ queryKey: ['ndt-progress-table', projectId] });
      setEditMap((prev) => { const n = { ...prev }; delete n[key]; return n; });
    } catch (err) { console.error('Save failed:', err); }
    setSaving((prev) => ({ ...prev, [key]: false }));
  };

  if (isLoading) return <div className="text-slate-400 p-6">Loading NDT data...</div>;

  return (
    <div className="space-y-6">
      {/* Two-column: STRUCTURAL (left) | PIPING (right) */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {NDT_DISCIPLINES.map((disc) => {
          const discRows = progressRows.filter((r: any) => r.discipline_name === disc.name);
          const discChartData = NDT_METHODS.map((method) => {
            const row = discRows.find((r: any) => r.ndt_method === method);
            return {
              ndt_method: method,
              pct: row ? Math.round((row.ndt_complete_length_mm / Math.max(row.rfi_total_length_mm, 1)) * 100) : 0,
              done: row?.ndt_complete_length_mm || 0,
              total: row?.rfi_total_length_mm || 0,
            };
          });
          const discTotalRfi = discRows.reduce((s: number, r: any) => s + (r.rfi_total_length_mm || 0), 0);
          const discTotalDone = discRows.reduce((s: number, r: any) => s + (r.ndt_complete_length_mm || 0), 0);
          const discTotalPct = discTotalRfi > 0 ? Math.round((discTotalDone / discTotalRfi) * 100) : 0;
          const discTotalTeam = discRows.reduce((s: number, r: any) => s + (r.team_deployed || 0), 0);
          const discTotalDaily = discRows.reduce((s: number, r: any) => s + (r.daily_length_done_mm || 0), 0);

          return (
            <Card key={disc.name}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full" style={{ backgroundColor: disc.color }} />
                  {disc.name} – NDT Daily Progress
                </CardTitle>
                <p className="text-xs text-slate-400 mt-1">RFI Total: {discTotalRfi.toLocaleString()} mm | Done: {discTotalDone.toLocaleString()} mm ({discTotalPct}%) | Team: {discTotalTeam} | Daily: {discTotalDaily.toLocaleString()} mm</p>
              </CardHeader>
              <CardContent>
                {/* Mini bar chart */}
                <div className="h-48 mb-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={discChartData}>
                      <XAxis dataKey="ndt_method" stroke="#94a3b8" fontSize={11} />
                      <YAxis stroke="#94a3b8" fontSize={10} unit="%" domain={[0, 100]} />
                      <Tooltip
                        contentStyle={{ background: '#1e293b', border: '1px solid #475569', borderRadius: '6px', color: '#e2e8f0', fontSize: '12px' }}
                        formatter={(value: number, name: string, props: any) => [`${value}% — ${props.payload.done?.toLocaleString()} / ${props.payload.total?.toLocaleString()} mm`, 'Completion']}
                        labelFormatter={(label: string) => `${disc.name} — ${label}`}
                      />
                      <Bar dataKey="pct" name="% Complete" radius={[3, 3, 0, 0]}>
                        {discChartData.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                {/* Progress table */}
                <div className="overflow-x-auto border border-slate-700/50 rounded-lg">
                  <table className="w-full text-xs border-collapse">
                    <thead>
                      <tr className="text-center text-slate-400 border-b border-slate-700 bg-slate-900/40">
                        <th className="py-1.5 pl-2 pr-1 text-left">Method</th>
                        <th className="py-1.5 px-1 w-16">RFI Total (mm)</th>
                        <th className="py-1.5 px-1 w-16">NDT Done (mm)</th>
                        <th className="py-1.5 px-1">%</th>
                        <th className="py-1.5 px-1 w-10">Team</th>
                        <th className="py-1.5 px-1 w-16">Daily Done (mm)</th>
                        <th className="py-1.5 px-1 w-36">Outstanding (RFI – Done)</th>
                        <th className="py-1.5 px-1 w-36">Remarks</th>
                        <th className="py-1.5 pr-2 w-16">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {NDT_METHODS.map((method) => {
                        const row = discRows.find((r: any) => r.ndt_method === method);
                        if (!row) return (
                          <tr key={method} className="border-b border-slate-800/50">
                            <td className="py-1.5 pl-2 pr-1">
                              <div className="flex items-center gap-1">
                                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: COLORS[NDT_METHODS.indexOf(method) % COLORS.length] }} />
                                <span className="font-bold text-white">{method}</span>
                              </div>
                            </td>
                            <td colSpan={8} className="py-1.5 text-slate-600 text-center">No data</td>
                          </tr>
                        );
                        const rfiTotal = row.rfi_total_length_mm || 1;
                        const ndtDone = row.ndt_complete_length_mm || 0;
                        const pct = Math.round((ndtDone / Math.max(rfiTotal, 1)) * 100);
                        const logKey = `${row.log_id}`;
                        const isEditing = editMap[logKey] !== undefined;
                        const isSaving = saving[logKey];
                        return (
                          <tr key={row.log_id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                            <td className="py-1.5 pl-2 pr-1">
                              <div className="flex items-center gap-1">
                                <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: COLORS[NDT_METHODS.indexOf(method) % COLORS.length] }} />
                                <span className="font-bold text-white">{method}</span>
                              </div>
                            </td>
                            <td className="py-1.5 px-1 font-mono text-white text-right">{rfiTotal.toLocaleString()}</td>
                            <td className="py-1.5 px-1 font-mono text-emerald-400 text-right font-semibold">{ndtDone.toLocaleString()}</td>
                            <td className="py-1.5 px-1">
                              <div className="flex items-center gap-1">
                                <Progress value={pct} className="flex-1 h-1" />
                                <span className="text-[10px] font-mono text-slate-400 w-6 text-right">{pct}%</span>
                              </div>
                            </td>
                            <td className="py-1.5 px-1 text-center">
                              {isEditing ? (
                                <input type="number" min={0} value={editMap[logKey].team}
                                  onChange={(e) => setEditMap((prev) => ({ ...prev, [logKey]: { ...prev[logKey], team: Number(e.target.value) } }))}
                                  className="w-10 bg-slate-800 border border-slate-600 rounded px-1 py-0 text-[10px] text-white text-center font-mono" />
                              ) : (<span className="font-mono text-white">{row.team_deployed || 0}</span>)}
                            </td>
                            <td className="py-1.5 px-1 text-center">
                              {isEditing ? (
                                <input type="number" min={0} value={editMap[logKey].dailyDone}
                                  onChange={(e) => setEditMap((prev) => ({ ...prev, [logKey]: { ...prev[logKey], dailyDone: Number(e.target.value) } }))}
                                  className="w-14 bg-slate-800 border border-slate-600 rounded px-1 py-0 text-[10px] text-white text-center font-mono" />
                              ) : (<span className="font-mono text-amber-400">{(row.daily_length_done_mm || 0).toLocaleString()}</span>)}
                            </td>
                            <td className="py-1.5 px-1 text-[10px] font-mono max-w-36 truncate block">
                              {(() => { const diff = rfiTotal - ndtDone; return diff <= 0 ? <span className="text-emerald-400">No outstanding</span> : <span className="text-amber-400">Outstanding {diff.toLocaleString()} mm</span>; })()}
                            </td>
                            <td className="py-1.5 px-1">
                              {isEditing ? (
                                <input type="text" value={editMap[logKey].remarks}
                                  onChange={(e) => setEditMap((prev) => ({ ...prev, [logKey]: { ...prev[logKey], remarks: e.target.value } }))}
                                  className="w-full bg-slate-800 border border-slate-600 rounded px-1 py-0 text-[10px] text-white" />
                              ) : (<span className="text-slate-500 text-[10px] max-w-36 truncate block" title={row.remarks}>{row.remarks || '-'}</span>)}
                            </td>
                            <td className="py-1.5 pr-2 text-center">
                              {isEditing ? (
                                <button onClick={() => handleSave(row)} disabled={isSaving}
                                  className="flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium rounded bg-emerald-800/60 text-emerald-300 hover:bg-emerald-700/60">
                                  <Save className="h-2.5 w-2.5" /> {isSaving ? '...' : 'Save'}
                                </button>
                              ) : (
                                <button onClick={() => handleStartEdit(row)}
                                  className="px-1.5 py-0.5 text-[10px] font-medium rounded border border-slate-600 text-slate-400 hover:text-white hover:border-slate-500">
                                  Update
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* NDT % Rules Reference */}
      <Card>
        <CardHeader>
          <CardTitle>NDT Test Percentage Requirements by Material Class</CardTitle>
          <p className="text-xs text-slate-400 mt-1">Applicable NDT % per material class. Ref: ASME V / project NDT plan.</p>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-center text-slate-400 border-b border-slate-700 bg-slate-900/40">
                  <th className="py-1.5 pl-3 pr-2 text-left">Material Class</th>
                  {NDT_METHODS.map((m) => <th key={m} className="py-1.5 px-2 w-16">{m}</th>)}
                </tr>
              </thead>
              <tbody>
                {Object.entries(NDT_RULES).map(([cls, rules], idx) => (
                  <tr key={cls} className={`border-b border-slate-800/50 ${idx % 2 === 0 ? 'bg-slate-900/20' : ''}`}>
                    <td className="py-1.5 pl-3 pr-2">
                      <Badge variant={cls.startsWith('pipe') ? 'info' : 'warning'}>{cls}</Badge>
                    </td>
                    {NDT_METHODS.map((m) => {
                      const val = rules[m] || '-';
                      const isFull = val === '100%';
                      const isPartial = val.includes('%') && !isFull;
                      return (
                        <td key={m} className={`py-1.5 px-2 text-center font-mono ${
                          isFull ? 'text-emerald-400 font-semibold' : isPartial ? 'text-amber-400' : 'text-slate-500'
                        }`}>{val}</td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* NDT Drawing Register */}
      <Card>
        <CardHeader>
          <CardTitle>NDT Drawing Register – AFC Drawings with NDT Scope</CardTitle>
          <p className="text-xs text-slate-400 mt-1">Only AFC drawings with material piece marks (NDT required). Click a drawing to view its NDT summary.</p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 mb-4">
            {NDT_DISCIPLINES.map((d) => {
              const isSelected = selectedDiscipline === d.name;
              return (
                <button key={d.name}
                  onClick={() => { setSelectedDiscipline(d.name); setSelectedDrawingId(null); setSelectedDrawingNumber(null); }}
                  className={`px-4 py-2 text-xs font-medium rounded-lg transition-all duration-200 ${
                    isSelected ? 'bg-slate-700 text-white border-2 border-white/30 shadow-lg'
                    : 'bg-slate-800/60 text-slate-400 border-2 border-slate-700/50 hover:border-slate-500/60 hover:text-slate-200'
                  }`}
                  style={{ borderTopColor: isSelected ? '#fff' : d.color, borderTopWidth: '3px' }}
                >{d.name}</button>
              );
            })}
          </div>
          {registerLoading ? (
            <div className="text-slate-400 py-4 text-center text-xs">Loading drawing register...</div>
          ) : disciplineRegisterDrawings.length === 0 ? (
            <div className="text-slate-500 py-4 text-center text-xs">No NDT-scope drawings found for {selectedDiscipline}</div>
          ) : (
            <div className="overflow-x-auto border border-slate-700/50 rounded-lg">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-slate-400 border-b border-slate-700 bg-slate-900/40">
                    <th className="py-2 pr-2 pl-3 w-10">S/No</th>
                    <th className="py-2 pr-2 w-20">Drawing ID</th>
                    <th className="py-2 pr-2">Drawing No</th>
                    <th className="py-2 pr-2">Discipline</th>
                    <th className="py-2 pr-2">Drawing Title</th>
                    <th className="py-2 pr-2 w-10">Rev</th>
                    <th className="py-2 pr-2 text-center w-22">Issued for Construction</th>
                    <th className="py-2 pr-2 w-24">Issued Date</th>
                    <th className="py-2 pr-2">Material Class</th>
                    <th className="py-2 pr-2 text-center w-16">Joint Count</th>
                    <th className="py-2 pr-2 text-right w-24">Total Length (m)</th>
                    <th className="py-2 pr-3 w-14">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {disciplineRegisterDrawings.map((drw: any, idx: number) => {
                    const isSelected = selectedDrawingId === drw.drawing_id;
                    return (
                    <tr key={drw.drawing_id}
                      onClick={() => { if (isSelected) { setSelectedDrawingId(null); setSelectedDrawingNumber(null); } else { setSelectedDrawingId(drw.drawing_id); setSelectedDrawingNumber(drw.drawing_number); } }}
                      className={`border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer ${isSelected ? 'bg-blue-900/30 border-l-2 border-l-blue-400' : ''}`}>
                      <td className="py-2.5 pr-2 pl-3 text-slate-500 text-xs">{idx + 1}</td>
                      <td className="py-2.5 pr-2 text-xs text-slate-500 font-mono" title={drw.drawing_id}>{drw.drawing_id.substring(0, 8)}...</td>
                      <td className="py-2.5 pr-2 font-mono text-white text-xs">{drw.drawing_number}</td>
                      <td className="py-2.5 pr-2 text-slate-300 text-xs">{drw.discipline_name}</td>
                      <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-40 truncate" title={drw.drawing_title}>{drw.drawing_title}</td>
                      <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs text-center">{drw.revision || '-'}</td>
                      <td className="py-2.5 pr-2 text-center"><Badge variant="success">AFC</Badge></td>
                      <td className="py-2.5 pr-2 text-xs text-slate-400">{drw.issued_for_construction_date || '-'}</td>
                      <td className="py-2.5 pr-2"><Badge variant={selectedDiscipline === 'PIPING' ? 'info' : 'warning'}>{drw.material_class || '-'}</Badge></td>
                      <td className="py-2.5 pr-2 font-mono text-white text-xs text-center">{drw.joint_count || '-'}</td>
                      <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{drw.total_length_m ? drw.total_length_m.toLocaleString() : '-'}</td>
                      <td className="py-2.5 pr-3">
                        <button onClick={(e) => { e.stopPropagation(); setSelectedDrawingId(null); setSelectedDrawingNumber(null); }}
                          className={`p-1 rounded transition-colors ${isSelected ? 'text-red-400 hover:bg-red-900/40' : 'text-slate-600'}`}
                          title="Clear selection"><X className="h-3.5 w-3.5" /></button>
                      </td>
                    </tr>
                  )})}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Per-Drawing NDT Summary */}
      {selectedDrawingId && selectedDrawingNumber && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4 text-blue-400" />NDT Summary – {selectedDrawingNumber}</CardTitle>
          </CardHeader>
          <CardContent>
            {ndtDrawingSummary.length === 0 ? (
              <div className="text-slate-500 py-4 text-center text-xs">No NDT records found for this drawing</div>
            ) : (
              <div className="overflow-x-auto border border-slate-700/50 rounded-lg">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs text-slate-400 border-b border-slate-700 bg-slate-900/40">
                      <th className="py-2 pr-2 pl-3 w-10">S/No</th>
                      <th className="py-2 pr-2">NDT Type</th>
                      <th className="py-2 pr-2 text-right">Total FP Joint (mm)</th>
                      <th className="py-2 pr-3 text-right">Total Weld (FP/FW) mm</th>
                      <th className="py-2 pr-3 text-center">Avg % Complete</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ndtDrawingSummary.map((item: any, idx: number) => (
                      <tr key={item.ndt_method} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                        <td className="py-2.5 pr-2 pl-3 text-slate-500 text-xs">{idx + 1}</td>
                        <td className="py-2.5 pr-2"><Badge variant={idx % 2 === 0 ? 'info' : 'warning'}>{item.ndt_method}</Badge></td>
                        <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{item.total_fp_joint_mm?.toLocaleString()}</td>
                        <td className="py-2.5 pr-3 font-mono text-white text-xs text-right font-semibold">{item.total_weld_mm?.toLocaleString()}</td>
                        <td className="py-2.5 pr-3 text-center">
                          <div className="flex items-center gap-2">
                            <Progress value={item.avg_pct || 0} className="flex-1 h-1.5" />
                            <span className="text-xs font-mono text-slate-400 w-10">{item.avg_pct || 0}%</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
