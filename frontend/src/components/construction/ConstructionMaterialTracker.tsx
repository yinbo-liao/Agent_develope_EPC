import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { apiClient } from '../../lib/api-client';
import { Package, FileText, CheckCircle, AlertTriangle, X, ChevronRight, AlertCircle } from 'lucide-react';

const COLORS: Record<string, string> = {
  STRUCTURAL: '#3b82f6',
  PIPING: '#8b5cf6',
  MECHANICAL: '#f59e0b',
  ELECTRICAL: '#10b981',
  HVAC: '#06b6d4',
};

const DISCIPLINES = [
  { name: 'STRUCTURAL', id: 1 },
  { name: 'PIPING', id: 2 },
  { name: 'MECHANICAL', id: 3 },
  { name: 'ELECTRICAL', id: 4 },
  { name: 'HVAC', id: 5 },
];

function isMaterialDiscipline(name: string): boolean {
  return name === 'STRUCTURAL' || name === 'PIPING';
}

function disciplineIdFromName(name: string): number {
  const map: Record<string, number> = { STRUCTURAL: 1, PIPING: 2, MECHANICAL: 3, ELECTRICAL: 4, HVAC: 5 };
  return map[name] || 0;
}

interface MvrStatusBadgeProps {
  status: string;
  isAfc: boolean;
  isAfi: boolean;
}

function MvrStatusBadge({ status, isAfc, isAfi }: MvrStatusBadgeProps) {
  let variant: 'default' | 'success' | 'warning' | 'info' | 'destructive' = 'default';
  let label = status || 'Info-AFI';

  switch (status) {
    case 'MVR-confirm':
      variant = 'success';
      break;
    case 'Structure-requested':
      variant = 'warning';
      break;
    case 'Info-AFI':
    default:
      variant = isAfi ? 'warning' : 'info';
      break;
  }

  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant={variant}>{label}</Badge>
      {status === 'MVR-confirm' && isAfi && (
        <span className="text-red-400 text-xs font-bold" title="AFI dwg only">!</span>
      )}
    </span>
  );
}

export function ConstructionMaterialTracker({ projectId }: { projectId: string }) {
  const [selectedDiscipline, setSelectedDiscipline] = useState<string>('STRUCTURAL');
  const [activeTab, setActiveTab] = useState<'planning' | 'confirmation'>('planning');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [selectedDrawingNumber, setSelectedDrawingNumber] = useState<string | null>(null);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [confirmMessage, setConfirmMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: materialsData, isLoading } = useQuery({
    queryKey: ['construction-materials', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/construction/materials/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  const { data: mvrSummary } = useQuery({
    queryKey: ['construction-mvr-summary', projectId],
    queryFn: () => apiClient.get(`/api/construction/mvr-summary/${projectId}`),
    refetchInterval: 10000,
  });

  const { data: drawingsData } = useQuery({
    queryKey: ['construction-drawings', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/drawings/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  const allDrawings: any[] = drawingsData?.data || [];
  const disciplineDrawings = allDrawings.filter((d: any) => d.discipline_name === selectedDiscipline);

  const materials = materialsData?.data?.materials || [];
  const equipment = materialsData?.data?.equipment || [];

  // Filter materials by selected drawing
  const filteredMaterials = selectedDrawingId
    ? materials.filter((m: any) => m.drawing_id === selectedDrawingId)
    : materials;

  // Group materials by drawing for the planning view
  const materialsByDrawing = useMemo(() => {
    const grouped: Record<string, any[]> = {};
    for (const m of materials) {
      if (!grouped[m.drawing_id]) grouped[m.drawing_id] = [];
      grouped[m.drawing_id].push(m);
    }
    return grouped;
  }, [materials]);

  // Procurement planning summary (aggregated) — filtered by selected drawing
  const procurementPlanning = useMemo(() => {
    const groups: Record<string, any> = {};
    for (const r of filteredMaterials) {
      const cat = r.material_category || r.material_type;
      const typ = r.material_type;
      const sz = r.size || r.diameter || '-';
      const thick = r.material_thickness || '-';
      const grade = r.material_grade || '-';
      const matClass = r.material_class || '-';
      const poStat = r.po_status || '-';
      const key = [cat, typ, sz, thick, grade, matClass, poStat].join('|');
      if (!groups[key]) {
        groups[key] = {
          material_category: cat,
          material_type: typ,
          size: sz,
          thickness: thick,
          grade: grade,
          material_class: matClass,
          po_status: poStat,
          count: 0,
          total_length_m: 0,
          total_weight_kg: 0,
        };
      }
      groups[key].count += 1;
      groups[key].total_length_m += r.material_length || 0;
      groups[key].total_weight_kg += r.total_weight || 0;
    }
    return Object.values(groups).sort((a: any, b: any) =>
      a.material_category.localeCompare(b.material_category) ||
      a.material_type.localeCompare(b.material_type)
    );
  }, [materials]);

  const handleConfirmMvr = async (materialId: string, newStatus: string) => {
    setConfirmingId(materialId);
    setConfirmMessage(null);
    try {
      const response = await apiClient.patch(`/api/construction/mvr-status/${materialId}`, {
        mvr_status: newStatus,
        confirmed_by: 'Trade Leader', // In real app, this would come from auth
      });
      const data = response.data;
      if (data.status === 'error') {
        setConfirmMessage(data.message || 'Failed to update MVR status');
      } else {
        if (data.warning) {
          setConfirmMessage(`MVR confirmed! Note: ${data.warning}`);
        } else {
          setConfirmMessage('MVR status updated successfully!');
        }
        queryClient.invalidateQueries({ queryKey: ['construction-materials', projectId] });
        queryClient.invalidateQueries({ queryKey: ['construction-mvr-summary', projectId] });
        // Also invalidate engineering materials since they share the same data
        queryClient.invalidateQueries({ queryKey: ['engineering-materials', projectId] });
      }
    } catch (err: any) {
      const msg = err.response?.data?.message || err.message || 'Failed to update MVR status';
      setConfirmMessage(msg);
    } finally {
      setConfirmingId(null);
      setTimeout(() => setConfirmMessage(null), 5000);
    }
  };

  const mvrSummaryData = mvrSummary?.data || [];

  return (
    <div className="space-y-6">
      {/* MVR Summary Cards */}
      {mvrSummaryData.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {mvrSummaryData.map((s: any) => (
            <div
              key={s.discipline_name}
              className="bg-slate-800/60 border border-slate-700/50 rounded-xl p-3"
              style={{ borderTopColor: COLORS[s.discipline_name] || '#64748b', borderTopWidth: '3px' }}
            >
              <div className="text-xs font-semibold text-white mb-2">{s.discipline_name}</div>
              <div className="space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-slate-400">Total</span>
                  <span className="font-mono text-white">{s.total_materials}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Info-AFI</span>
                  <span className="font-mono text-amber-400">{s.info_afi_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Structure-requested</span>
                  <span className="font-mono text-orange-400">{s.structure_requested_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">MVR-confirm</span>
                  <span className="font-mono text-emerald-400">{s.mvr_confirm_count}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Discipline Selector */}
      <div className="flex flex-wrap gap-2">
        {DISCIPLINES.map((d) => {
          const isSelected = selectedDiscipline === d.name;
          return (
            <button
              key={d.name}
              onClick={() => {
                setSelectedDiscipline(d.name);
                setSelectedDrawingId(null);
                setSelectedDrawingNumber(null);
              }}
              className={`px-4 py-2 text-xs font-medium rounded-lg transition-all duration-200 ${
                isSelected
                  ? 'bg-slate-700 text-white border-2 border-white/30 shadow-lg'
                  : 'bg-slate-800/60 text-slate-400 border-2 border-slate-700/50 hover:border-slate-500/60 hover:text-slate-200'
              }`}
              style={{ borderTopColor: isSelected ? '#fff' : COLORS[d.name], borderTopWidth: '3px' }}
            >
              {d.name}
            </button>
          );
        })}
      </div>

      {/* Tab Selector for Material Disciplines */}
      {isMaterialDiscipline(selectedDiscipline) && (
        <div className="flex gap-1 bg-slate-900/60 rounded-lg p-1 w-fit">
          <button
            onClick={() => setActiveTab('planning')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'planning' ? 'bg-primary text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Package className="h-3.5 w-3.5" /> Material Planning
          </button>
          <button
            onClick={() => setActiveTab('confirmation')}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              activeTab === 'confirmation' ? 'bg-primary text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <CheckCircle className="h-3.5 w-3.5" /> Material Confirmation
          </button>
        </div>
      )}

      {/* Confirmation Message */}
      {confirmMessage && (
        <div className={`p-3 rounded-lg text-sm ${
          confirmMessage.includes('error') || confirmMessage.includes('Cannot')
            ? 'bg-red-950/40 border border-red-800/50 text-red-300'
            : 'bg-emerald-950/40 border border-emerald-800/50 text-emerald-300'
        }`}>
          {confirmMessage}
        </div>
      )}

      {isLoading ? (
        <div className="text-slate-400 py-8 text-center">Loading construction data...</div>
      ) : isMaterialDiscipline(selectedDiscipline) ? (
        /* ===== STRUCTURAL / PIPING VIEW ===== */
        activeTab === 'planning' ? (
          /* ===== MATERIAL PLANNING TAB ===== */
          <div className="space-y-6">
            {/* Drawing List with Materials */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Drawing List – {selectedDiscipline}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                        <th className="py-2 pr-2 w-10">S/No</th>
                        <th className="py-2 pr-2">Drawing No</th>
                        <th className="py-2 pr-2">Drawing Title</th>
                        <th className="py-2 pr-2 w-12">Rev</th>
                        <th className="py-2 pr-2 text-center w-16">Status</th>
                        <th className="py-2 pr-2 text-center w-20">Materials</th>
                        <th className="py-2 pr-2 text-right w-24">Total Wt (kg)</th>
                        <th className="py-2 w-14">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {disciplineDrawings.map((drw: any, idx: number) => {
                        const drawingMats = materialsByDrawing[drw.drawing_id] || [];
                        const totalWeight = drawingMats.reduce((s: number, m: any) => s + (m.total_weight || 0), 0);
                        const isSelected = selectedDrawingId === drw.drawing_id;
                        const hasPrRaised = drawingMats.some((m: any) => m.po_status === 'PR-Raised');
                        return (
                          <tr
                            key={drw.drawing_id}
                            onClick={() => {
                              if (isSelected) {
                                setSelectedDrawingId(null);
                                setSelectedDrawingNumber(null);
                              } else {
                                setSelectedDrawingId(drw.drawing_id);
                                setSelectedDrawingNumber(drw.drawing_number);
                              }
                            }}
                            className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer ${
                              isSelected ? 'bg-blue-900/30 border-l-2 border-l-blue-400' : ''
                            } ${hasPrRaised ? 'bg-green-900/20' : ''}`}
                          >
                            <td className="py-2.5 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                            <td className="py-2.5 pr-2 font-mono text-white text-xs">{drw.drawing_number}</td>
                            <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-40 truncate" title={drw.drawing_title}>{drw.drawing_title}</td>
                            <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs text-center">{drw.revision || '-'}</td>
                            <td className="py-2.5 pr-2 text-center">
                              <Badge variant={drw.issued_for_construction === 'Yes' ? 'success' : drw.issued_for_info === 'Yes' ? 'warning' : 'default'}>
                                {drw.issued_for_construction === 'Yes' ? 'AFC' : drw.issued_for_info === 'Yes' ? 'AFI' : 'WIP'}
                              </Badge>
                            </td>
                            <td className="py-2.5 pr-2 text-center font-mono text-xs text-slate-300">{drawingMats.length}</td>
                            <td className="py-2.5 pr-2 text-right font-mono text-xs text-white">{totalWeight.toLocaleString()}</td>
                            <td className="py-2.5">
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setSelectedDrawingId(isSelected ? null : drw.drawing_id);
                                  setSelectedDrawingNumber(isSelected ? null : drw.drawing_number);
                                }}
                                className="p-1 rounded hover:bg-slate-700/40 text-slate-500 hover:text-white transition-colors"
                              >
                                <ChevronRight className={`h-3.5 w-3.5 transition-transform ${isSelected ? 'rotate-90' : ''}`} />
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Material Detail Table */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Package className="h-4 w-4" />
                  Material Details – {selectedDiscipline}
                  {selectedDrawingNumber && (
                    <span className="text-xs text-blue-400 font-normal ml-2">
                      (Filtered: {selectedDrawingNumber})
                    </span>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {selectedDrawingId && selectedDrawingNumber && (
                  <div className="flex items-center justify-between p-3 bg-blue-950/40 border border-blue-800/50 rounded-lg mb-3">
                    <div className="flex items-center gap-2 text-sm">
                      <FileText className="h-4 w-4 text-blue-400" />
                      <span className="text-slate-300">Filtered to drawing:</span>
                      <span className="font-mono font-semibold text-blue-300">{selectedDrawingNumber}</span>
                      <span className="text-slate-500">({filteredMaterials.length} material{filteredMaterials.length !== 1 ? 's' : ''})</span>
                    </div>
                    <button
                      onClick={() => { setSelectedDrawingId(null); setSelectedDrawingNumber(null); }}
                      className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
                    >
                      <X className="h-3 w-3" /> Clear Filter
                    </button>
                  </div>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border-collapse">
                    <thead>
                      <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                        <th className="py-2 pr-2 w-10">S/No</th>
                        <th className="py-2 pr-2">Drawing No</th>
                        <th className="py-2 pr-2 w-12">Rev</th>
                        <th className="py-2 pr-2">Piece Mark</th>
                        <th className="py-2 pr-2">Material Grade</th>
                        <th className="py-2 pr-2">Thickness</th>
                        <th className="py-2 pr-2">Material Type</th>
                        <th className="py-2 pr-2">Category</th>
                        <th className="py-2 pr-2">{selectedDiscipline === 'PIPING' ? 'Pipe OD' : 'Size'}</th>
                        <th className="py-2 pr-2 text-right">Unit Wt</th>
                        <th className="py-2 pr-2 text-right">Length (m)</th>
                        <th className="py-2 pr-2 text-right">Total Wt (kg)</th>
                        <th className="py-2 pr-2 text-center">Drawing Status</th>
                        <th className="py-2 pr-2 text-center">MVR Status</th>
                        <th className="py-2 pr-2 text-center">PO Status</th>
                        <th className="py-2 w-10">Remark</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredMaterials.map((m: any, idx: number) => {
                        const hasPrRaised = m.po_status === 'PR-Raised';
                        const isAfiWarning = m.mvr_status === 'MVR-confirm' && m.is_afi;
                        return (
                          <tr
                            key={m.material_id}
                            className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${
                              hasPrRaised ? 'bg-green-900/20' : ''
                            }`}
                          >
                            <td className="py-2 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                            <td className="py-2 pr-2 font-mono text-white text-xs">{m.drawing_number}</td>
                            <td className="py-2 pr-2 font-mono text-slate-300 text-xs text-center">{m.drawing_rev || '-'}</td>
                            <td className="py-2 pr-2 font-mono text-slate-300 text-xs">{m.piece_mark || '-'}</td>
                            <td className="py-2 pr-2 text-slate-400 text-xs">{m.material_grade || '-'}</td>
                            <td className="py-2 pr-2 text-slate-400 text-xs">{m.material_thickness || '-'}</td>
                            <td className="py-2 pr-2 text-slate-300 text-xs"><Badge>{m.material_type}</Badge></td>
                            <td className="py-2 pr-2"><Badge variant="info">{m.material_category || '-'}</Badge></td>
                            <td className="py-2 pr-2 text-slate-400 text-xs">{m.size || m.diameter || '-'}</td>
                            <td className="py-2 pr-2 font-mono text-slate-400 text-xs text-right">{m.material_weight?.toLocaleString()}</td>
                            <td className="py-2 pr-2 font-mono text-white text-xs text-right">{m.material_length?.toLocaleString() || '-'}</td>
                            <td className="py-2 pr-2 font-mono text-white text-xs text-right font-semibold">{m.total_weight?.toLocaleString()}</td>
                            <td className="py-2 pr-2 text-center">
                              <Badge variant={m.is_afc ? 'success' : m.is_afi ? 'warning' : 'default'}>
                                {m.is_afc ? 'AFC' : m.is_afi ? 'AFI' : 'WIP'}
                              </Badge>
                            </td>
                            <td className="py-2 pr-2 text-center">
                              <MvrStatusBadge status={m.mvr_status} isAfc={m.is_afc} isAfi={m.is_afi} />
                            </td>
                            <td className="py-2 pr-2 text-center">
                              {(() => {
                                const displayPoStatus = selectedDiscipline === 'PIPING' && m.po_status === 'Structure-requested'
                                  ? 'piping-requested'
                                  : m.po_status;
                                const badgeVariant = m.po_status === 'PR-Raised' ? 'success' :
                                  m.po_status === 'Structure-requested' ? 'warning' : 'default';
                                return (
                                  <Badge variant={badgeVariant}>
                                    {displayPoStatus || '-'}
                                  </Badge>
                                );
                              })()}
                            </td>
                            <td className="py-2 text-center">
                              {isAfiWarning && (
                                <span className="text-red-400 text-xs font-bold" title="AFI dwg only">!</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      {filteredMaterials.length === 0 && (
                        <tr><td colSpan={16} className="py-6 text-center text-slate-500">No materials found</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Procurement Planning Summary — only per selected drawing */}
            {selectedDrawingId && procurementPlanning.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Package className="h-4 w-4 text-amber-400" />
                    Procurement Planning – Material Summary
                    <span className="text-xs text-blue-400 font-normal ml-1">
                      ({selectedDrawingNumber})
                    </span>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                          <th className="py-2 pr-2">Material Category</th>
                          <th className="py-2 pr-2">Material Type</th>
                          <th className="py-2 pr-2">{selectedDiscipline === 'PIPING' ? 'Pipe OD' : 'Size'}</th>
                          <th className="py-2 pr-2">Thickness</th>
                          <th className="py-2 pr-2">Grade</th>
                          <th className="py-2 pr-2 text-center">Count</th>
                          <th className="py-2 pr-2 text-right">Total Length (m)</th>
                          <th className="py-2 pr-2 text-right">Total Weight (kg)</th>
                          <th className="py-2 pr-2">Material Class</th>
                          <th className="py-2">PO Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {procurementPlanning.map((p: any, idx: number) => (
                          <tr key={idx} className={`border-b border-slate-800/50 ${
                            p.po_status === 'PR-Raised' ? 'bg-green-900/20' : ''
                          }`}>
                            <td className="py-2.5 pr-2"><Badge variant={selectedDiscipline === 'PIPING' ? 'info' : 'warning'}>{p.material_category}</Badge></td>
                            <td className="py-2.5 pr-2 text-slate-300 text-xs">{p.material_type}</td>
                            <td className="py-2.5 pr-2 text-slate-400 text-xs">{p.size}</td>
                            <td className="py-2.5 pr-2 text-slate-400 text-xs">{p.thickness}</td>
                            <td className="py-2.5 pr-2 text-slate-400 text-xs">{p.grade}</td>
                            <td className="py-2.5 pr-2 font-mono text-white text-xs text-center">{p.count}</td>
                            <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{p.total_length_m?.toLocaleString()}</td>
                            <td className="py-2.5 pr-2 font-mono text-white text-xs text-right font-semibold">{p.total_weight_kg?.toLocaleString()}</td>
                            <td className="py-2.5 pr-2"><Badge variant="info">{p.material_class}</Badge></td>
                            <td className="py-2.5">
                              {(() => {
                                const displayPoStatus = selectedDiscipline === 'PIPING' && p.po_status === 'Structure-requested'
                                  ? 'piping-requested'
                                  : p.po_status;
                                const badgeVariant = p.po_status === 'PR-Raised' ? 'success' :
                                  p.po_status === 'Structure-requested' ? 'warning' : 'default';
                                return (
                                  <Badge variant={badgeVariant}>
                                    {displayPoStatus}
                                  </Badge>
                                );
                              })()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-3 p-3 bg-slate-800/50 border border-slate-700/50 rounded-lg text-xs text-slate-400 space-y-1">
                    <p><span className="font-semibold text-slate-300">Info-AFI:</span> Drawing approved for information</p>
                    {selectedDiscipline === 'PIPING' ? (
                      <p><span className="font-semibold text-slate-300">piping-requested:</span> Piping team requested to order</p>
                    ) : (
                      <p><span className="font-semibold text-slate-300">Structure-requested:</span> Structure team requested to order</p>
                    )}
                    <p><span className="font-semibold text-slate-300">PR-Raised:</span> Material confirmed and purchase order created</p>
                    <p><span className="font-semibold text-slate-300">MVR-confirm:</span> Material verified and confirmed by trade leader</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        ) : (
          /* ===== MATERIAL CONFIRMATION TAB ===== */
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <CheckCircle className="h-4 w-4" />
                Material Confirmation – {selectedDiscipline}
              </CardTitle>
              <p className="text-xs text-slate-400 mt-1">
                Trade leader can confirm MVR status. Only AFC drawings can be MVR-confirmed.
              </p>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                      <th className="py-2 pr-2 w-10">S/No</th>
                      <th className="py-2 pr-2">Drawing No</th>
                      <th className="py-2 pr-2">Piece Mark</th>
                      <th className="py-2 pr-2">Material Type</th>
                      <th className="py-2 pr-2">Category</th>
                      <th className="py-2 pr-2 text-right">Total Wt (kg)</th>
                      <th className="py-2 pr-2 text-center">Drawing Status</th>
                      <th className="py-2 pr-2 text-center">Current MVR</th>
                      <th className="py-2 pr-2 text-center">Set Structure-requested</th>
                      <th className="py-2 text-center">Set MVR-confirm</th>
                    </tr>
                  </thead>
                  <tbody>
                    {materials.map((m: any, idx: number) => {
                      const isConfirming = confirmingId === m.material_id;
                      const canConfirm = m.is_afc; // Only AFC can be MVR-confirmed
                      return (
                        <tr key={m.material_id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${
                          m.po_status === 'PR-Raised' ? 'bg-green-900/20' : ''
                        }`}>
                          <td className="py-2.5 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                          <td className="py-2.5 pr-2 font-mono text-white text-xs">{m.drawing_number}</td>
                          <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs">{m.piece_mark || '-'}</td>
                          <td className="py-2.5 pr-2 text-slate-300 text-xs"><Badge>{m.material_type}</Badge></td>
                          <td className="py-2.5 pr-2"><Badge variant="info">{m.material_category || '-'}</Badge></td>
                          <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{m.total_weight?.toLocaleString()}</td>
                          <td className="py-2.5 pr-2 text-center">
                            <Badge variant={m.is_afc ? 'success' : m.is_afi ? 'warning' : 'default'}>
                              {m.is_afc ? 'AFC' : m.is_afi ? 'AFI' : 'WIP'}
                            </Badge>
                          </td>
                          <td className="py-2.5 pr-2 text-center">
                            <MvrStatusBadge status={m.mvr_status} isAfc={m.is_afc} isAfi={m.is_afi} />
                          </td>
                          <td className="py-2.5 pr-2 text-center">
                            <button
                              onClick={() => handleConfirmMvr(m.material_id, 'Structure-requested')}
                              disabled={isConfirming || m.mvr_status === 'Structure-requested' || m.mvr_status === 'MVR-confirm'}
                              className={`px-2 py-1 text-xs font-medium rounded-md transition-colors ${
                                m.mvr_status === 'Structure-requested' || m.mvr_status === 'MVR-confirm'
                                  ? 'bg-slate-700/30 text-slate-500 cursor-not-allowed'
                                  : 'bg-orange-900/40 text-orange-300 hover:bg-orange-800/50 border border-orange-700/50'
                              }`}
                            >
                              {isConfirming ? '...' : m.mvr_status === 'Structure-requested' ? '✓' : 'Request'}
                            </button>
                          </td>
                          <td className="py-2.5 text-center">
                            <button
                              onClick={() => handleConfirmMvr(m.material_id, 'MVR-confirm')}
                              disabled={isConfirming || !canConfirm || m.mvr_status === 'MVR-confirm'}
                              className={`px-2 py-1 text-xs font-medium rounded-md transition-colors ${
                                !canConfirm || m.mvr_status === 'MVR-confirm'
                                  ? 'bg-slate-700/30 text-slate-500 cursor-not-allowed'
                                  : 'bg-emerald-900/40 text-emerald-300 hover:bg-emerald-800/50 border border-emerald-700/50'
                              }`}
                              title={!canConfirm ? 'Drawing must be AFC to confirm MVR' : 'Confirm MVR status'}
                            >
                              {isConfirming ? '...' : m.mvr_status === 'MVR-confirm' ? '✓ Confirmed' : 'Confirm'}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {materials.length === 0 && (
                      <tr><td colSpan={10} className="py-6 text-center text-slate-500">No materials found for {selectedDiscipline}</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        )
      ) : (
        /* ===== MECHANICAL / ELECTRICAL / HVAC VIEW ===== */
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="h-4 w-4" />
              Equipment – {selectedDiscipline}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                    <th className="py-2 pr-2 w-10">S/No</th>
                    <th className="py-2 pr-2">Drawing No</th>
                    <th className="py-2 pr-2 w-12">Rev</th>
                    <th className="py-2 pr-2">Equipment Tag</th>
                    <th className="py-2 pr-2">Equipment Detail</th>
                    <th className="py-2 pr-2">Install Location</th>
                    <th className="py-2 pr-2 text-right">Weight (kg)</th>
                    <th className="py-2 pr-2 text-center">Drawing Status</th>
                    <th className="py-2 text-center">FAT Status</th>
                  </tr>
                </thead>
                <tbody>
                  {equipment.map((e: any, idx: number) => (
                    <tr key={e.equipment_id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                      <td className="py-2.5 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                      <td className="py-2.5 pr-2 font-mono text-white text-xs">{e.drawing_number}</td>
                      <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs text-center">{e.drawing_rev || '-'}</td>
                      <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs">{e.equipment_tag}</td>
                      <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-40 truncate" title={e.equipment_detail}>{e.equipment_detail}</td>
                      <td className="py-2.5 pr-2 text-slate-400 text-xs">{e.install_location || '-'}</td>
                      <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{e.weight?.toLocaleString()}</td>
                      <td className="py-2.5 pr-2 text-center">
                        <Badge variant={e.issued_for_construction === 'Yes' ? 'success' : e.issued_for_info === 'Yes' ? 'warning' : 'default'}>
                          {e.issued_for_construction === 'Yes' ? 'AFC' : e.issued_for_info === 'Yes' ? 'AFI' : 'WIP'}
                        </Badge>
                      </td>
                      <td className="py-2.5 text-center">
                        <Badge variant={e.fat_status === 'APPROVED' ? 'success' : e.fat_status === 'PENDING' ? 'warning' : 'default'}>
                          {e.fat_status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                  {equipment.length === 0 && (
                    <tr><td colSpan={9} className="py-6 text-center text-slate-500">No equipment found for {selectedDiscipline}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
