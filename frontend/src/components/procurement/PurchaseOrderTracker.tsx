import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { apiClient } from '../../lib/api-client';
import { useOptionalAuth } from '../../auth/context';
import { Package, FileText, X, Plus, Loader2 } from 'lucide-react';

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

/** PO statuses accepted by the backend (keep in sync with dev_main.py). */
const PO_STATUSES = [
  'Info-AFI',
  'Structure-requested',
  'piping-requested',
  'PR-Raised',
  'PO-issued',
  'Delivered',
] as const;

/** Roles allowed to add material records and change PO status. */
const ENGINEERING_WRITE_ROLES = ['admin', 'project_manager', 'trade_lead'];

/** Options for a status select; keeps an unrecognised stored value selectable. */
function statusOptions(current?: string | null): string[] {
  const base: string[] = [...PO_STATUSES];
  return current && !base.includes(current) ? [current, ...base] : base;
}

const EMPTY_MATERIAL_FORM = {
  drawing_id: '',
  piece_mark: '',
  material_category: '',
  material_type: '',
  size: '',
  material_thickness: '',
  material_grade: '',
  material_class: '',
  material_length: '',
  material_weight: '',
  total_weight: '',
  po_status: 'Info-AFI',
};

type MaterialForm = typeof EMPTY_MATERIAL_FORM;

export function PurchaseOrderTracker({ projectId }: { projectId: string }) {
  const [selectedDiscipline, setSelectedDiscipline] = useState<string>('STRUCTURAL');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [selectedDrawingNumber, setSelectedDrawingNumber] = useState<string | null>(null);
  const [showAddForm, setShowAddForm] = useState(false);
  const [form, setForm] = useState<MaterialForm>(EMPTY_MATERIAL_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savingStatusId, setSavingStatusId] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const auth = useOptionalAuth();
  const canEdit = ENGINEERING_WRITE_ROLES.includes(auth?.user?.role ?? '');
  const inputCls =
    'w-full bg-slate-900 border border-slate-700 rounded px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-blue-500';

  const { data: drawingsData, isLoading: drawingsLoading } = useQuery({
    queryKey: ['procurement-drawings', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/drawings/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  const { data: materialsData, isLoading: materialsLoading } = useQuery({
    queryKey: ['procurement-materials', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/materials/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline)}`),
  });

  // main.py returns {items, pagination}; dev_main returns a bare list.
  const rawDrawings = drawingsData?.data;
  const allDrawings: any[] = Array.isArray(rawDrawings) ? rawDrawings : rawDrawings?.items || [];
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

  const openAddForm = () => {
    setForm({
      ...EMPTY_MATERIAL_FORM,
      drawing_id: selectedDrawingId || allDrawings[0]?.drawing_id || '',
    });
    setFormError(null);
    setShowAddForm(true);
  };

  const updateForm = (field: keyof MaterialForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const refreshMaterialQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['procurement-drawings', projectId] });
    queryClient.invalidateQueries({ queryKey: ['procurement-materials', projectId] });
    queryClient.invalidateQueries({ queryKey: ['engineering-drawings', projectId] });
    queryClient.invalidateQueries({ queryKey: ['engineering-materials', projectId] });
    queryClient.invalidateQueries({ queryKey: ['engineering-summary', projectId] });
  };

  const handleCreateMaterial = async () => {
    if (!canEdit || saving) return;
    if (!form.drawing_id) {
      setFormError('Select a drawing first.');
      return;
    }
    if (!form.material_type.trim()) {
      setFormError('Material type is required.');
      return;
    }
    setSaving(true);
    setFormError(null);
    const numberOf = (value: string) => (value.trim() === '' ? null : Number(value));
    try {
      await apiClient.post(`/api/engineering/materials/${projectId}`, {
        drawing_id: form.drawing_id,
        material_type: form.material_type.trim(),
        material_category: form.material_category.trim() || null,
        piece_mark: form.piece_mark.trim() || null,
        material_grade: form.material_grade.trim() || null,
        material_thickness: form.material_thickness.trim() || null,
        size: form.size.trim() || null,
        material_class: form.material_class.trim() || null,
        material_length: numberOf(form.material_length),
        material_weight: numberOf(form.material_weight),
        total_weight: numberOf(form.total_weight),
        po_status: form.po_status || null,
      });
      refreshMaterialQueries();
      setSelectedDrawingId(form.drawing_id);
      const drw = allDrawings.find((d: any) => d.drawing_id === form.drawing_id);
      setSelectedDrawingNumber(drw?.drawing_number ?? null);
      setShowAddForm(false);
      setForm(EMPTY_MATERIAL_FORM);
    } catch (err: any) {
      setFormError(err?.response?.data?.detail || 'Failed to create material record.');
    } finally {
      setSaving(false);
    }
  };

  const handleStatusChange = async (materialId: string, poStatus: string) => {
    if (!canEdit) return;
    setSavingStatusId(materialId);
    setStatusError(null);
    try {
      await apiClient.patch(`/api/engineering/materials/${projectId}/${materialId}/status`, {
        po_status: poStatus,
      });
      refreshMaterialQueries();
    } catch (err: any) {
      setStatusError(err?.response?.data?.detail || 'Failed to update PO status.');
    } finally {
      setSavingStatusId(null);
    }
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
                  {canEdit && (
                    <button
                      onClick={openAddForm}
                      disabled={allDrawings.length === 0}
                      className="ml-auto flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white transition-colors"
                      title="Add a material record to a drawing"
                    >
                      <Plus className="h-3.5 w-3.5" />
                      Add Material
                    </button>
                  )}
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

              {/* Add Material Record (engineering team only) */}
              {canEdit && showAddForm && (
                <div className="border border-blue-700/50 bg-blue-950/10 rounded-lg overflow-hidden">
                  <div className="px-4 py-3 bg-blue-950/30 flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-blue-300 flex items-center gap-2">
                      <Plus className="h-4 w-4" />
                      Add Material Record – {selectedDiscipline}
                    </h3>
                    <button
                      onClick={() => { setShowAddForm(false); setFormError(null); }}
                      className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-700/50"
                      title="Cancel"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="p-4 space-y-3">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                      <div>
                        <label htmlFor="material-drawing" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Drawing</label>
                        <select
                          id="material-drawing"
                          value={form.drawing_id}
                          onChange={(e) => updateForm('drawing_id', e.target.value)}
                          className={inputCls}
                        >
                          <option value="">Select drawing…</option>
                          {allDrawings.map((d: any) => (
                            <option key={d.drawing_id} value={d.drawing_id}>{d.drawing_number}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor="material-piece-mark" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Piece Mark</label>
                        <input id="material-piece-mark" value={form.piece_mark} onChange={(e) => updateForm('piece_mark', e.target.value)} className={inputCls} placeholder="e.g. P-101" />
                      </div>
                      <div>
                        <label htmlFor="material-category" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Material Category</label>
                        <input id="material-category" value={form.material_category} onChange={(e) => updateForm('material_category', e.target.value)} className={inputCls} placeholder="e.g. Steel Plate" />
                      </div>
                      <div>
                        <label htmlFor="material-type" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Material Type <span className="text-red-400">*</span></label>
                        <input id="material-type" value={form.material_type} onChange={(e) => updateForm('material_type', e.target.value)} className={inputCls} placeholder="e.g. Pipe" />
                      </div>
                      <div>
                        <label htmlFor="material-size" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Size</label>
                        <input id="material-size" value={form.size} onChange={(e) => updateForm('size', e.target.value)} className={inputCls} placeholder="e.g. 6 inch" />
                      </div>
                      <div>
                        <label htmlFor="material-thickness" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Thickness</label>
                        <input id="material-thickness" value={form.material_thickness} onChange={(e) => updateForm('material_thickness', e.target.value)} className={inputCls} placeholder="e.g. 10 mm" />
                      </div>
                      <div>
                        <label htmlFor="material-grade" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Grade</label>
                        <input id="material-grade" value={form.material_grade} onChange={(e) => updateForm('material_grade', e.target.value)} className={inputCls} placeholder="e.g. CS" />
                      </div>
                      <div>
                        <label htmlFor="material-class" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Material Class</label>
                        <input id="material-class" value={form.material_class} onChange={(e) => updateForm('material_class', e.target.value)} className={inputCls} placeholder="e.g. A106" />
                      </div>
                      <div>
                        <label htmlFor="material-length" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Length (m)</label>
                        <input id="material-length" type="number" min="0" step="any" value={form.material_length} onChange={(e) => updateForm('material_length', e.target.value)} className={inputCls} placeholder="0" />
                      </div>
                      <div>
                        <label htmlFor="material-unit-weight" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Unit Weight (kg/m)</label>
                        <input id="material-unit-weight" type="number" min="0" step="any" value={form.material_weight} onChange={(e) => updateForm('material_weight', e.target.value)} className={inputCls} placeholder="0" />
                      </div>
                      <div>
                        <label htmlFor="material-total-weight" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">Total Weight (kg)</label>
                        <input id="material-total-weight" type="number" min="0" step="any" value={form.total_weight} onChange={(e) => updateForm('total_weight', e.target.value)} className={inputCls} placeholder="auto = unit weight × length" />
                      </div>
                      <div>
                        <label htmlFor="material-po-status" className="block text-[10px] uppercase tracking-wide text-slate-400 mb-1">PO Status</label>
                        <select id="material-po-status" value={form.po_status} onChange={(e) => updateForm('po_status', e.target.value)} className={inputCls}>
                          {PO_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                      </div>
                    </div>
                    {formError && <p className="text-xs text-red-400">{formError}</p>}
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => { setShowAddForm(false); setFormError(null); }}
                        className="px-3 py-1.5 text-xs rounded-lg bg-slate-800 text-slate-300 hover:bg-slate-700"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCreateMaterial}
                        disabled={saving}
                        className="flex items-center gap-1 px-4 py-1.5 text-xs font-medium rounded-lg bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 text-white"
                      >
                        {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
                        {saving ? 'Saving…' : 'Add Record'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

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

                      {/* Individual material records – PO status control (engineering team only) */}
                      {canEdit && drawingMaterials.length > 0 && (
                        <div className="border-t border-slate-700/50">
                          <div className="px-4 py-2 bg-slate-900/40 text-[10px] uppercase tracking-wide text-slate-400 flex items-center justify-between">
                            <span>Material Records – PO Status Control</span>
                            {savingStatusId && (
                              <span className="flex items-center gap-1 text-blue-400 normal-case">
                                <Loader2 className="h-3 w-3 animate-spin" /> Saving…
                              </span>
                            )}
                          </div>
                          {statusError && <p className="px-4 py-2 text-xs text-red-400">{statusError}</p>}
                          <div className="overflow-x-auto max-h-64 overflow-y-auto">
                            <table className="w-full text-sm border-collapse">
                              <thead>
                                <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                                  <th className="py-2 pl-4 pr-2">Piece Mark</th>
                                  <th className="py-2 pr-2">Category</th>
                                  <th className="py-2 pr-2">Type</th>
                                  <th className="py-2 pr-2">Size</th>
                                  <th className="py-2 pr-2 text-right">Length (m)</th>
                                  <th className="py-2 pr-2 text-right">Weight (kg)</th>
                                  <th className="py-2 pr-4">PO Status</th>
                                </tr>
                              </thead>
                              <tbody>
                                {drawingMaterials.map((m: any) => (
                                  <tr key={m.material_id} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                                    <td className="py-2 pl-4 pr-2 font-mono text-xs text-white">{m.piece_mark || '-'}</td>
                                    <td className="py-2 pr-2 text-xs text-slate-300">{m.material_category || '-'}</td>
                                    <td className="py-2 pr-2 text-xs text-slate-300">{m.material_type || '-'}</td>
                                    <td className="py-2 pr-2 text-xs text-slate-400">{m.size || m.diameter || '-'}</td>
                                    <td className="py-2 pr-2 font-mono text-xs text-right text-slate-300">{m.material_length ?? 0}</td>
                                    <td className="py-2 pr-2 font-mono text-xs text-right text-slate-300">{m.total_weight ?? 0}</td>
                                    <td className="py-2 pr-4">
                                      <div className="flex items-center gap-2">
                                        <select
                                          aria-label={`PO status for ${m.piece_mark || m.material_id}`}
                                          value={m.po_status || 'Info-AFI'}
                                          onChange={(e) => handleStatusChange(m.material_id, e.target.value)}
                                          disabled={savingStatusId === m.material_id}
                                          className={`${inputCls} w-44`}
                                        >
                                          {statusOptions(m.po_status).map((s) => <option key={s} value={s}>{s}</option>)}
                                        </select>
                                        {savingStatusId === m.material_id && (
                                          <Loader2 className="h-3 w-3 animate-spin text-blue-400" />
                                        )}
                                      </div>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
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
