import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { apiClient } from '../../lib/api-client';
import { Package, FileText, X } from 'lucide-react';

const PROCUREMENT_DISCIPLINES = [
  { name: 'STRUCTURAL', id: 1, color: '#3b82f6' },
  { name: 'PIPING', id: 2, color: '#8b5cf6' },
  { name: 'ELECTRICAL', id: 4, color: '#10b981' },
  { name: 'MECHANICAL', id: 3, color: '#f59e0b' },
  { name: 'HVAC', id: 5, color: '#06b6d4' },
];

function disciplineIdFromName(name: string): number {
  const map: Record<string, number> = { STRUCTURAL: 1, PIPING: 2, MECHANICAL: 3, ELECTRICAL: 4, HVAC: 5 };
  return map[name] || 0;
}

const STRUCTURAL_CAT_ORDER: Record<string, number> = {
  'Steel Plate': 0, 'Bulb Plate': 1, 'Angle Bar': 2, 'I-BEAM': 3, 'FlatBar': 4, 'Pipe': 5,
};
const PIPING_TYPE_ORDER: Record<string, number> = {
  'Pipe': 0, 'Flange': 1, 'Elbow': 2, 'Tee': 3, 'Reducer': 4, 'Blank': 5, 'Bellow': 6, 'Bolt/Nuts': 7, 'Weldolet': 8,
};
const MATERIAL_GRADE_ORDER: Record<string, number> = {
  'CS': 0, 'SS': 1, 'DSS': 2, 'CUNI': 3, 'GRE': 4, 'TI': 5,
};

export function PurchaseOrderTracker({ projectId }: { projectId: string }) {
  const [selectedDiscipline, setSelectedDiscipline] = useState<string>('STRUCTURAL');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [selectedDrawingNumber, setSelectedDrawingNumber] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data: drawingsData, isLoading: drawingsLoading } = useQuery({
    queryKey: ['procurement-drawings', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/drawings/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  const { data: materialsData, isLoading: materialsLoading } = useQuery({
    queryKey: ['procurement-materials', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/materials/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  const allDrawings: any[] = drawingsData?.data || [];
  const allMaterials: any[] = materialsData?.data?.items || [];

  // Group materials by drawing_id
  const materialsByDrawing = useMemo(() => {
    const grouped: Record<string, any[]> = {};
    for (const m of allMaterials) {
      if (!grouped[m.drawing_id]) grouped[m.drawing_id] = [];
      grouped[m.drawing_id].push(m);
    }
    return grouped;
  }, [allMaterials]);

  const handleDeleteDrawing = async (drawingId: string, drawingNumber: string) => {
    if (!window.confirm(`Delete drawing "${drawingNumber}" and all related materials/equipment? This cannot be undone.`)) return;
    try {
      await apiClient.delete(`/api/engineering/drawings/${projectId}/${drawingId}`);
      queryClient.invalidateQueries({ queryKey: ['procurement-drawings', projectId] });
      queryClient.invalidateQueries({ queryKey: ['procurement-materials', projectId] });
      queryClient.invalidateQueries({ queryKey: ['engineering-drawings', projectId] });
      queryClient.invalidateQueries({ queryKey: ['engineering-materials', projectId] });
      queryClient.invalidateQueries({ queryKey: ['engineering-summary', projectId] });
    } catch (err) { console.error('Failed to delete drawing:', err); }
  };

  // Aggregate materials for summary table (similar to procurement_planning)
  function aggregateMaterials(items: any[], discipline: string) {
    const groups: Record<string, any> = {};
    for (const r of items) {
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
    if (discipline === 'PIPING') {
      return Object.values(groups).sort((a: any, b: any) => {
        const typeA = PIPING_TYPE_ORDER[a.material_type] ?? 99;
        const typeB = PIPING_TYPE_ORDER[b.material_type] ?? 99;
        if (typeA !== typeB) return typeA - typeB;
        const matA = MATERIAL_GRADE_ORDER[a.material_category] ?? 99;
        const matB = MATERIAL_GRADE_ORDER[b.material_category] ?? 99;
        return matA - matB;
      });
    }
    return Object.values(groups).sort((a: any, b: any) => {
      const catA = STRUCTURAL_CAT_ORDER[a.material_category] ?? 99;
      const catB = STRUCTURAL_CAT_ORDER[b.material_category] ?? 99;
      if (catA !== catB) return catA - catB;
      const gradeA = MATERIAL_GRADE_ORDER[a.material_class] ?? 99;
      const gradeB = MATERIAL_GRADE_ORDER[b.material_class] ?? 99;
      return gradeA - gradeB;
    });
  }

  const isLoading = drawingsLoading || materialsLoading;

  return (
    <div className="space-y-6">
      {/* Discipline Tabs */}
      <Card>
        <CardHeader>
          <CardTitle>Procurement – Material Planning by Discipline</CardTitle>
          <p className="text-xs text-slate-400 mt-1">Click a drawing to view its material summary</p>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2 mb-4">
            {PROCUREMENT_DISCIPLINES.map((d) => {
              const isSelected = selectedDiscipline === d.name;
              return (
                <button
                  key={d.name}
                  onClick={() => setSelectedDiscipline(d.name)}
                  className={`px-4 py-2 text-xs font-medium rounded-lg transition-all duration-200 ${
                    isSelected
                      ? 'bg-slate-700 text-white border-2 border-white/30 shadow-lg'
                      : 'bg-slate-800/60 text-slate-400 border-2 border-slate-700/50 hover:border-slate-500/60 hover:text-slate-200'
                  }`}
                  style={{ borderTopColor: isSelected ? '#fff' : d.color, borderTopWidth: '3px' }}
                >
                  {d.name}
                </button>
              );
            })}
          </div>

          {isLoading ? (
            <div className="text-slate-400 py-8 text-center">Loading procurement data...</div>
          ) : (
            <div className="space-y-8">
              {/* Drawing List Table */}
              <div>
                <h3 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Drawing List – {selectedDiscipline}
                  <Badge variant="info">{allDrawings.length} drawings</Badge>
                </h3>
                {allDrawings.length === 0 ? (
                  <div className="text-slate-500 py-4 text-center text-xs">
                    <Package className="h-6 w-6 mx-auto mb-1 opacity-40" />
                    <p>No drawings found for {selectedDiscipline}</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto border border-slate-700/50 rounded-lg">
                    <table className="w-full text-sm border-collapse">
                      <thead>
                        <tr className="text-left text-xs text-slate-400 border-b border-slate-700 bg-slate-900/40">
                          <th className="py-2 pr-2 pl-4 w-10">S/No</th>
                          <th className="py-2 pr-2 w-28">Drawing ID</th>
                          <th className="py-2 pr-2">Drawing No</th>
                          <th className="py-2 pr-2">Discipline</th>
                          <th className="py-2 pr-2">Drawing Title</th>
                          <th className="py-2 pr-2 w-12">Rev</th>
                          <th className="py-2 pr-2 text-center w-20">Issued for Info</th>
                          <th className="py-2 pr-2 w-24">Issued Date</th>
                          <th className="py-2 pr-2 text-center w-22">Issued for Construction</th>
                          <th className="py-2 w-24">Issued Date</th>
                          <th className="py-2 pr-4 w-14">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {allDrawings.map((drw: any, idx: number) => {
                          const isAfc = drw.issued_for_construction === 'Yes';
                          const isAfi = drw.issued_for_info === 'Yes' && !isAfc;
                          return (
                          <tr
                            key={drw.drawing_id}
                            onClick={() => {
                              if (selectedDrawingId === drw.drawing_id) {
                                setSelectedDrawingId(null);
                                setSelectedDrawingNumber(null);
                              } else {
                                setSelectedDrawingId(drw.drawing_id);
                                setSelectedDrawingNumber(drw.drawing_number);
                              }
                            }}
                            className={`border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors cursor-pointer ${
                              selectedDrawingId === drw.drawing_id
                                ? 'bg-blue-900/30 border-l-2 border-l-blue-400'
                                : isAfc ? 'bg-emerald-950/15' : isAfi ? 'bg-amber-950/10' : ''
                            }`}
                          >
                            <td className="py-2.5 pr-2 pl-4 text-slate-500 text-xs">{idx + 1}</td>
                            <td className="py-2.5 pr-2 text-xs text-slate-500 font-mono" title={drw.drawing_id}>{drw.drawing_id.substring(0, 8)}...</td>
                            <td className="py-2.5 pr-2 font-mono text-white text-xs">{drw.drawing_number}</td>
                            <td className="py-2.5 pr-2 text-slate-300 text-xs">{drw.discipline_name}</td>
                            <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-40 truncate" title={drw.drawing_title}>{drw.drawing_title}</td>
                            <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs text-center">{drw.revision || '-'}</td>
                            <td className="py-2.5 pr-2 text-center">
                              {isAfi ? (
                                <Badge variant="info">AFI</Badge>
                              ) : (
                                <Badge variant={drw.issued_for_info === 'Yes' ? 'success' : 'default'}>
                                  {drw.issued_for_info === 'Yes' ? 'Yes' : '-'}
                                </Badge>
                              )}
                            </td>
                            <td className="py-2.5 pr-2 text-xs text-slate-400">{drw.issued_for_info_date || '-'}</td>
                            <td className="py-2.5 text-center">
                              {isAfc ? (
                                <Badge variant="success">AFC</Badge>
                              ) : (
                                <Badge variant="warning">-</Badge>
                              )}
                            </td>
                            <td className="py-2.5 text-xs text-slate-400">{drw.issued_for_construction_date || '-'}</td>
                            <td className="py-2.5 pr-4">
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteDrawing(drw.drawing_id, drw.drawing_number); }}
                                className="p-1 rounded hover:bg-red-900/40 text-slate-500 hover:text-red-400 transition-colors"
                                title={`Delete ${drw.drawing_number}`}
                              >
                                <X className="h-3.5 w-3.5" />
                              </button>
                            </td>
                          </tr>
                        )})}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Material Summary for Selected Drawing */}
              <div>
                <h3 className="text-sm font-semibold text-blue-400 mb-3 flex items-center gap-2">
                  <FileText className="h-4 w-4" />
                  Material Summary
                </h3>
                {!selectedDrawingId ? (
                  <div className="text-slate-500 py-8 text-center border border-slate-700/50 rounded-lg">
                    <Package className="h-8 w-8 mx-auto mb-2 opacity-40" />
                    <p className="text-sm">Select a drawing from the list above</p>
                    <p className="text-xs text-slate-600 mt-1">to view its procurement material summary</p>
                  </div>
                ) : (() => {
                  const selDrw = allDrawings.find((d: any) => d.drawing_id === selectedDrawingId);
                  if (!selDrw) return <div className="text-slate-500 py-4 text-center text-xs">Drawing not found</div>;
                  const drawingMaterials = materialsByDrawing[selectedDrawingId] || [];
                  const summary = aggregateMaterials(drawingMaterials, selectedDiscipline);
                  const isAfc = selDrw.issued_for_construction === 'Yes';
                  const isAfi = selDrw.issued_for_info === 'Yes' && !isAfc;

                  return (
                    <div className={`border rounded-lg overflow-hidden ${
                      isAfc ? 'border-emerald-700/50 bg-emerald-950/10' :
                      isAfi ? 'border-amber-800/40 bg-amber-950/10' :
                      'border-slate-700/50'
                    }`}>
                      {/* Drawing Header */}
                      <div className={`px-4 py-3 flex items-center justify-between flex-wrap gap-2 ${
                        isAfc ? 'bg-emerald-950/30' : isAfi ? 'bg-amber-950/30' : 'bg-slate-800/80'
                      }`}>
                        <div className="flex items-center gap-2">
                          <FileText className={`h-4 w-4 ${isAfc ? 'text-emerald-400' : isAfi ? 'text-amber-400' : 'text-blue-400'}`} />
                          <span className="font-mono text-white text-sm font-semibold">{selDrw.drawing_number}</span>
                          {isAfc ? <Badge variant="success">AFC</Badge> : isAfi ? <Badge variant="warning">AFI - Not Approved</Badge> : null}
                        </div>
                        <span className="text-xs text-slate-400" title={selDrw.drawing_title}>
                          {selDrw.drawing_title || ''}
                          {selDrw.revision && <span className="ml-2">Rev: {selDrw.revision}</span>}
                        </span>
                      </div>

                      {/* Material Summary Table */}
                      {drawingMaterials.length === 0 ? (
                        <div className="px-4 py-3 text-xs text-slate-500">No materials associated with this drawing</div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="w-full text-sm border-collapse">
                            <thead>
                              <tr className={`text-left text-xs text-slate-400 border-b ${
                                isAfi ? 'border-amber-800/40 bg-amber-950/20' : 'border-slate-700 bg-slate-900/40'
                              }`}>
                                <th className="py-2 pl-4 pr-2">Material Category</th>
                                <th className="py-2 pr-2">Material Type</th>
                                <th className="py-2 pr-2">Size</th>
                                <th className="py-2 pr-2">Thickness</th>
                                <th className="py-2 pr-2">Grade</th>
                                <th className="py-2 pr-2 text-center">Count</th>
                                <th className="py-2 pr-2 text-right">Total Length (m)</th>
                                <th className="py-2 pr-2 text-right">Total Weight (kg)</th>
                                <th className="py-2 pr-2">Material Class</th>
                                <th className="py-2 pr-4">PO Status</th>
                              </tr>
                            </thead>
                            <tbody>
                              {summary.map((item: any, idx: number) => (
                                <tr key={idx} className={`border-b ${
                                  isAfi ? 'border-amber-800/20 bg-amber-950/15 hover:bg-amber-950/30' : 'border-slate-800/50 hover:bg-slate-800/20'
                                } ${item.po_status === 'PR-Raised' ? 'bg-green-900/20' : ''}`}>
                                  <td className="py-2.5 pl-4 pr-2"><Badge variant="warning">{item.material_category}</Badge></td>
                                  <td className="py-2.5 pr-2 text-slate-300 text-xs">{item.material_type}</td>
                                  <td className="py-2.5 pr-2 text-slate-400 text-xs">{item.size}</td>
                                  <td className="py-2.5 pr-2 text-slate-400 text-xs">{item.thickness}</td>
                                  <td className="py-2.5 pr-2 text-slate-400 text-xs">{item.grade}</td>
                                  <td className="py-2.5 pr-2 font-mono text-white text-xs text-center">{item.count}</td>
                                  <td className="py-2.5 pr-2 font-mono text-white text-xs text-right">{item.total_length_m?.toLocaleString()}</td>
                                  <td className="py-2.5 pr-2 font-mono text-white text-xs text-right font-semibold">{item.total_weight_kg?.toLocaleString()}</td>
                                  <td className="py-2.5 pr-2"><Badge variant="info">{item.material_class}</Badge></td>
                                  <td className="py-2.5 pr-4">
                                    <Badge variant={
                                      item.po_status === 'PR-Raised' ? 'success' :
                                      item.po_status === 'Structure-requested' ? 'warning' : 'default'
                                    }>
                                      {item.po_status}
                                    </Badge>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {/* Drawing material total */}
                      {drawingMaterials.length > 0 && (
                        <div className={`px-4 py-2 border-t text-xs text-slate-400 flex justify-end gap-4 ${
                          isAfi ? 'bg-amber-950/20 border-amber-800/40' : 'bg-slate-900/40 border-slate-700/50'
                        }`}>
                          <span>Total materials: <span className="font-mono text-white">{drawingMaterials.length}</span></span>
                          <span>Total weight: <span className="font-mono text-white font-semibold">
                            {drawingMaterials.reduce((s: number, m: any) => s + (m.total_weight || 0), 0).toLocaleString()} kg
                          </span></span>
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
