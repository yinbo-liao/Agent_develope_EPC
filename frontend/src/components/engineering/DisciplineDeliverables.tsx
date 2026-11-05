import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Progress } from '../ui/Progress';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { ErrorBanner } from '../ui/ErrorBanner';
import { LoadingSkeleton, CardSkeleton, TableSkeleton } from '../ui/LoadingSkeleton';
import { ConfirmDialog } from '../ui/ConfirmDialog';
import { apiClient } from '../../lib/api-client';
import { CsvImport } from './CsvImport';
import {
  disciplineIdFromName, isMaterialDiscipline, isEquipmentDiscipline,
  PIPING_TYPE_ORDER, STRUCTURAL_CATEGORY_ORDER, MATERIAL_CATEGORY_ORDER,
} from '../../lib/discipline-utils';
import { CheckCircle, ChevronRight, Package, Wrench, FileText, X, BarChart3, ExternalLink, RefreshCw } from 'lucide-react';

const COLORS: Record<string, string> = {
  STRUCTURAL: '#3b82f6',
  PIPING: '#8b5cf6',
  MECHANICAL: '#f59e0b',
  ELECTRICAL: '#10b981',
  HVAC: '#06b6d4',
};

interface ChangeSummary {
  drawings_added: number;
  drawings_deleted: number;
  materials_added: number;
  materials_deleted: number;
}

// Discipline categories for material vs equipment
const STRUCTURAL_MATERIAL_COLS = ['material_type', 'piece_mark', 'material_grade', 'material_thickness', 'size', 'material_weight', 'total_weight'];
const PIPING_MATERIAL_COLS = ['material_type', 'piece_mark', 'material_grade', 'material_thickness', 'diameter', 'material_weight', 'total_weight'];

export function DisciplineDeliverables({ projectId }: { projectId: string }) {
  const [selectedDiscipline, setSelectedDiscipline] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'drawings' | 'materials'>('drawings');
  const [selectedDrawingId, setSelectedDrawingId] = useState<string | null>(null);
  const [selectedDrawingNumber, setSelectedDrawingNumber] = useState<string | null>(null);

  // ConfirmDialog state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmConfig, setConfirmConfig] = useState<{
    title: string; message: string; onConfirm: () => void;
  }>({ title: '', message: '', onConfirm: () => {} });

  const queryClient = useQueryClient();
  const disciplineCardsRef = useRef<HTMLDivElement>(null);

  const handleMtoDisciplineClick = (disciplineName: string) => {
    setSelectedDiscipline(disciplineName);
    setActiveTab('drawings');
    setTimeout(() => {
      disciplineCardsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const { data: summaryData, isLoading } = useQuery({
    queryKey: ['engineering-summary', projectId],
    queryFn: () => apiClient.get(`/api/engineering/summary/${projectId}`),
  });
  const { data: drawingsData } = useQuery({
    queryKey: ['engineering-drawings', projectId],
    queryFn: () => apiClient.get(`/api/engineering/drawings/${projectId}`),
  });
  const { data: materialsData } = useQuery({
    queryKey: ['engineering-materials', projectId, selectedDiscipline, selectedDrawingId],
    queryFn: () => {
      let url = `/api/engineering/materials/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline || '')}`;
      if (selectedDrawingId) url += `&drawing_id=${selectedDrawingId}`;
      return apiClient.get(url);
    },
    enabled: !!selectedDiscipline && isMaterialDiscipline(selectedDiscipline),
  });
  const { data: equipmentData } = useQuery({
    queryKey: ['engineering-equipment', projectId, selectedDiscipline],
    queryFn: () => apiClient.get(`/api/engineering/equipment/${projectId}?discipline_id=${disciplineIdFromName(selectedDiscipline || '')}`),
    enabled: !!selectedDiscipline && isEquipmentDiscipline(selectedDiscipline),
  });
  const { data: changeSummaryData } = useQuery({
    queryKey: ['engineering-change-summary', projectId],
    queryFn: () => apiClient.get(`/api/engineering/change-summary/${projectId}`),
    refetchInterval: 30000,
  });
  const changeSummary: ChangeSummary = changeSummaryData?.data || {
    drawings_added: 0, drawings_deleted: 0, materials_added: 0, materials_deleted: 0,
  };

  const handleDeleteDrawing = async (drawingId: string, drawingNumber: string) => {
    setConfirmConfig({
      title: 'Delete Drawing',
      message: `Delete drawing "${drawingNumber}" and all related materials/equipment? This cannot be undone.`,
      onConfirm: async () => {
        try {
          await apiClient.delete(`/api/engineering/drawings/${projectId}/${drawingId}`);
          queryClient.invalidateQueries({ queryKey: ['engineering-drawings', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-materials', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-equipment', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-summary', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-change-summary', projectId] });
          if (selectedDrawingId === drawingId) { setSelectedDrawingId(null); setSelectedDrawingNumber(null); }
        } catch (err) { console.error('Failed to delete drawing:', err); }
      },
    });
    setConfirmOpen(true);
  };

  const handleDeleteMaterial = async (materialId: string, pieceMark: string) => {
    setConfirmConfig({
      title: 'Delete Material',
      message: `Delete material "${pieceMark}"? This cannot be undone.`,
      onConfirm: async () => {
        try {
          await apiClient.delete(`/api/engineering/materials/${projectId}/${materialId}`);
          queryClient.invalidateQueries({ queryKey: ['engineering-materials', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-summary', projectId] });
          queryClient.invalidateQueries({ queryKey: ['engineering-change-summary', projectId] });
        } catch (err) { console.error('Failed to delete material:', err); }
      },
    });
    setConfirmOpen(true);
  };

  const summary = summaryData?.data;
  const allDrawings: any[] = drawingsData?.data || [];
  const materials = materialsData?.data;
  const equipment = equipmentData?.data;

  if (isLoading) return (
    <div className="p-6 space-y-4">
      <CardSkeleton />
      <TableSkeleton rows={5} cols={6} />
    </div>
  );

  if (!summary && !isLoading) return (
    <ErrorBanner
      title="Failed to load engineering data"
      message="Could not retrieve engineering summary from the server."
      onRetry={() => queryClient.invalidateQueries({ queryKey: ['engineering-summary', projectId] })}
    />
  );
  if (!summary) return null;

  const disciplines = summary.drawings || [];
  const totalAllDrawings = disciplines.reduce((s: number, d: any) => s + d.total_drawings, 0);
  const disciplineDrawings = allDrawings.filter((d: any) => d.discipline_name === selectedDiscipline);

  return (
    <div className="space-y-6">
      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={confirmConfig.onConfirm}
        title={confirmConfig.title}
        message={confirmConfig.message}
        variant="danger"
      />
      {/* Clickable Discipline Selector Cards */}
      <div ref={disciplineCardsRef} className="grid gap-3 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {disciplines.map((d: any) => {
          const color = COLORS[d.discipline_name] || '#64748b';
          const isSelected = selectedDiscipline === d.discipline_name;
          return (
            <button
              key={d.discipline_name}
              onClick={() => {
                setSelectedDiscipline(isSelected ? null : d.discipline_name);
                setActiveTab('drawings');
              }}
              className={`text-left transition-all duration-200 rounded-xl border-2 p-4 ${
                isSelected
                  ? 'border-white/30 bg-slate-700/80 shadow-lg scale-[1.02]'
                  : 'border-slate-700/50 bg-slate-800/60 hover:border-slate-500/60 hover:bg-slate-800'
              }`}
              style={{ borderTopColor: isSelected ? '#fff' : color, borderTopWidth: '3px' }}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-white text-sm truncate">{d.discipline_name}</span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium text-white shrink-0" style={{ backgroundColor: color }}>
                  {d.total_drawings}
                </span>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between"><span className="text-slate-400">IFA</span><span className="font-mono text-slate-300">{d.ifa_pct}%</span></div>
                <Progress value={d.ifa_pct} className="h-1" />
                <div className="flex justify-between"><span className="text-slate-400">IFC</span><span className="font-mono text-slate-300">{d.ifc_pct}%</span></div>
                <Progress value={d.ifc_pct} className="h-1" />
              </div>
              {isSelected && <ChevronRight className="h-4 w-4 text-white/60 mt-1 mx-auto rotate-90" />}
            </button>
          );
        })}
      </div>

      {/* Overall IFC Progress Bar */}
      <Card>
        <CardHeader><CardTitle>Overall Drawing Status – All Disciplines ({totalAllDrawings} drawings)</CardTitle></CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
            {disciplines.map((d: any) => (
              <div key={d.discipline_name} className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[d.discipline_name] }} />
                  <span className="text-xs text-slate-400 truncate">{d.discipline_name}</span>
                </div>
                <div className="flex justify-between text-xs"><span>IFC</span><span className="font-mono">{d.ifc_pct}%</span></div>
                <Progress value={d.ifc_pct} className="h-1.5" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Change Summary Panel */}
      <ChangeSummaryPanel summary={changeSummary} />

      {/* Selected Discipline Detail */}
      {selectedDiscipline && (
        <Card className="border-l-4" style={{ borderLeftColor: COLORS[selectedDiscipline] || '#64748b' }}>
          <CardHeader>
            <div className="flex items-center justify-between flex-wrap gap-3">
              <div>
                <CardTitle>{selectedDiscipline} – Detailed View</CardTitle>
                <p className="text-xs text-slate-400 mt-1">
                  {disciplineDrawings.length} drawings | IFA: {disciplines.find((d: any) => d.discipline_name === selectedDiscipline)?.ifa_pct}% | IFC: {disciplines.find((d: any) => d.discipline_name === selectedDiscipline)?.ifc_pct}%
                </p>
              </div>
              <div className="flex gap-1 bg-slate-900/60 rounded-lg p-1">
                <button
                  onClick={() => setActiveTab('drawings')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    activeTab === 'drawings' ? 'bg-primary text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  <FileText className="h-3.5 w-3.5" /> Drawings
                </button>
                <button
                  onClick={() => setActiveTab('materials')}
                  className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    activeTab === 'materials' ? 'bg-primary text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {isMaterialDiscipline(selectedDiscipline) ? <><Package className="h-3.5 w-3.5" /> Materials</> : <><Wrench className="h-3.5 w-3.5" /> Equipment</>}
                </button>
              </div>
            </div>
            {/* CSV Import */}
            <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-slate-700/50">
              {activeTab === 'drawings' ? (
                <CsvImport projectId={projectId} importType="drawings" label={`${selectedDiscipline} Drawings`}
                  queryKey={['engineering-drawings', projectId]}
                  sampleColumns={['Drawing No', 'Discipline', 'Drawing Title', 'Rev', 'Issued for Info', 'Issued Date', 'Issued for Construction', 'Issued Date']} />
              ) : isMaterialDiscipline(selectedDiscipline) ? (
                <CsvImport projectId={projectId} importType="materials" label={`${selectedDiscipline} Materials`}
                  queryKey={['engineering-materials', projectId, selectedDiscipline]}
                  sampleColumns={['Drawing No', 'Rev', 'Piece Mark', 'Material Grade', 'Thickness', 'Material Type', 'Size', 'Material Cat', 'Unit Wt (kg/m)', 'Length (m)', 'Total Wt (kg)']} />
              ) : (
                <CsvImport projectId={projectId} importType="equipment" label={`${selectedDiscipline} Equipment`}
                  queryKey={['engineering-equipment', projectId, selectedDiscipline]}
                  sampleColumns={['Drawing No', 'Rev', 'Equipment Tag', 'Equipment Name', 'Equipment Detail', 'Install Location', 'Weight (kg)', 'Equipment Type', 'Certification', 'FAT Status', 'Test Status', 'System Code', 'System Name', 'Delivery Date', 'Install Date', 'Remark']} />
              )}
            </div>
          </CardHeader>
          <CardContent>
            {activeTab === 'drawings' ? (
              /* ===== DRAWINGS TABLE ===== */
              <div className="overflow-x-auto">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                      <th className="py-2 pr-2 w-10">S/No</th>
                      <th className="py-2 pr-2 w-28">Drawing ID</th>
                      <th className="py-2 pr-2">Drawing No</th>
                      <th className="py-2 pr-2">Discipline</th>
                      <th className="py-2 pr-2">Drawing Title</th>
                      <th className="py-2 pr-2 w-12">Rev</th>
                      <th className="py-2 pr-2 text-center w-20">Issued for Info</th>
                      <th className="py-2 pr-2 w-24">Issued Date</th>
                      <th className="py-2 pr-2 text-center w-22">Issued for Construction</th>
                      <th className="py-2 w-24">Issued Date</th>
                      <th className="py-2 w-14">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {disciplineDrawings.map((drw: any, idx: number) => {
                      const isSelected = selectedDrawingId === drw.drawing_id;
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
                            setActiveTab('materials');
                          }
                        }}
                        className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer ${
                          isSelected ? 'bg-blue-900/30 border-l-2 border-l-blue-400' : ''
                        }`}
                      >
                        <td className="py-2.5 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                        <td className="py-2.5 pr-2 text-xs text-slate-500 font-mono">{drw.drawing_id}</td>
                        <td className="py-2.5 pr-2 font-mono text-white text-xs">{drw.drawing_number}</td>
                        <td className="py-2.5 pr-2 text-slate-300 text-xs">{drw.discipline_name}</td>
                        <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-40 truncate" title={drw.drawing_title}>{drw.drawing_title}</td>
                        <td className="py-2.5 pr-2 font-mono text-slate-300 text-xs text-center">{drw.revision || '-'}</td>
                        <td className="py-2.5 pr-2 text-center">
                          <Badge variant={drw.issued_for_info === 'Yes' ? 'success' : 'default'}>{drw.issued_for_info}</Badge>
                        </td>
                        <td className="py-2.5 pr-2 text-xs text-slate-400">{drw.issued_for_info_date || '-'}</td>
                        <td className="py-2.5 text-center">
                          <Badge variant={drw.issued_for_construction === 'Yes' ? 'success' : 'warning'}>{drw.issued_for_construction}</Badge>
                        </td>
                        <td className="py-2.5 text-xs text-slate-400">{drw.issued_for_construction_date || '-'}</td>
                        <td className="py-2.5">
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
            ) : isMaterialDiscipline(selectedDiscipline) ? (
              /* ===== STRUCTURAL / PIPING MATERIAL TABLE ===== */
              <MaterialTable
                discipline={selectedDiscipline}
                materials={materials}
                selectedDrawingId={selectedDrawingId}
                selectedDrawingNumber={selectedDrawingNumber}
                onClearFilter={() => { setSelectedDrawingId(null); setSelectedDrawingNumber(null); }}
                onDeleteMaterial={handleDeleteMaterial}
              />
            ) : (
              /* ===== MECHANICAL / ELECTRICAL / HVAC EQUIPMENT TABLE ===== */
              <EquipmentTable
                discipline={selectedDiscipline}
                equipment={equipment}
                selectedDrawingId={selectedDrawingId}
                selectedDrawingNumber={selectedDrawingNumber}
                onClearFilter={() => { setSelectedDrawingId(null); setSelectedDrawingNumber(null); }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {/* MTO Summary */}
      <Card>
        <CardHeader>
          <CardTitle>Material Take-Off (MTO) Total Weight by Discipline</CardTitle>
          <p className="text-xs text-slate-400 mt-1">Click a discipline to jump to its detail view</p>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead><tr className="text-left text-slate-400 border-b border-slate-700"><th className="py-2">Discipline</th><th className="py-2 text-right">MTO Weight (kg)</th></tr></thead>
            <tbody>
              {summary.mto_weights?.map((m: any) => (
                <tr
                  key={m.discipline_name}
                  onClick={() => handleMtoDisciplineClick(m.discipline_name)}
                  className="border-b border-slate-800 hover:bg-slate-800/30 transition-colors cursor-pointer group"
                >
                  <td className="py-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="info">{m.discipline_name}</Badge>
                      <ExternalLink className="h-3 w-3 text-slate-600 group-hover:text-blue-400 transition-colors opacity-0 group-hover:opacity-100" />
                    </div>
                  </td>
                  <td className="py-2 font-mono text-right">{ (m.mto_weight_kg || 0).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

/* ===== MATERIAL TABLE (Structural & Piping) ===== */
function MaterialTable({ discipline, materials, selectedDrawingId, selectedDrawingNumber, onClearFilter, onDeleteMaterial }: {
  discipline: string; materials: any;
  selectedDrawingId: string | null; selectedDrawingNumber: string | null;
  onClearFilter: () => void; onDeleteMaterial: (materialId: string, pieceMark: string) => void;
}) {
  if (!materials) return <div className="text-slate-400 py-6 text-center">Loading material data...</div>;
  const allItems = materials.items || [];
  const planning = materials.procurement_planning || [];
  const isPiping = discipline === 'PIPING';

  const items = selectedDrawingId
    ? allItems.filter((m: any) => m.drawing_id === selectedDrawingId)
    : allItems;

  return (
    <div className="space-y-6">
      {/* Material Detail Table */}
      <div>
        <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Package className="h-4 w-4" />
          Material Details – {discipline}
        </h4>
        {/* Filter Banner */}
        {selectedDrawingId && selectedDrawingNumber && (
          <div className="flex items-center justify-between p-3 bg-blue-950/40 border border-blue-800/50 rounded-lg mb-3">
            <div className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4 text-blue-400" />
              <span className="text-slate-300">Filtered to drawing:</span>
              <span className="font-mono font-semibold text-blue-300">{selectedDrawingNumber}</span>
              <span className="text-slate-500">({items.length} material{items.length !== 1 ? 's' : ''})</span>
            </div>
            <button
              onClick={onClearFilter}
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
                <th className="py-2 pr-2 w-28">Material ID</th>
                <th className="py-2 pr-2">Drawing No</th>
                <th className="py-2 pr-2 w-12">Rev</th>
                <th className="py-2 pr-2">Piece Mark</th>
                <th className="py-2 pr-2">Material Grade</th>
                <th className="py-2 pr-2">Thickness</th>
                {isPiping && <th className="py-2 pr-2">Material Type</th>}
                <th className="py-2 pr-2">{isPiping ? 'Material Cat' : 'Material Category'}</th>
                {isPiping ? <th className="py-2 pr-2">Pipe OD</th> : <th className="py-2 pr-2">Size</th>}
                <th className="py-2 pr-2 text-right">Unit Wt (kg/m)</th>
                <th className="py-2 pr-2 text-right">Length (m)</th>
                <th className="py-2 pr-2 text-right">Total Wt (kg)</th>
                <th className="py-2 pr-2 text-center">IFA</th>
                <th className="py-2 text-center">IFC</th>
                <th className="py-2 w-14">Action</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m: any, idx: number) => (
                <tr key={m.material_id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${
                  m.po_status === 'PR-Raised' ? 'bg-green-900/20' : ''
                }`}>
                  <td className="py-2 pr-2 text-slate-500 text-xs">{idx + 1}</td>
                  <td className="py-2 pr-2 text-xs text-slate-500 font-mono">{m.material_id}</td>
                  <td className="py-2 pr-2 font-mono text-white text-xs">{m.drawing_number}</td>
                  <td className="py-2 pr-2 font-mono text-slate-300 text-xs text-center">{m.drawing_rev || '-'}</td>
                  <td className="py-2 pr-2 font-mono text-slate-300 text-xs">{m.piece_mark || '-'}</td>
                  <td className="py-2 pr-2 text-slate-400 text-xs">{m.material_grade || '-'}</td>
                  <td className="py-2 pr-2 text-slate-400 text-xs">{m.material_thickness || '-'}</td>
                  {isPiping && <td className="py-2 pr-2 text-slate-300 text-xs"><Badge>{m.material_type}</Badge></td>}
                  <td className="py-2 pr-2">{isPiping ? <Badge variant="info">{m.material_category || '-'}</Badge> : <Badge>{m.material_category || m.material_type}</Badge>}</td>
                  <td className="py-2 pr-2 text-slate-400 text-xs">{isPiping ? (m.diameter || '-') : (m.size || '-')}</td>
                  <td className="py-2 pr-2 font-mono text-slate-400 text-xs text-right">{m.material_weight?.toLocaleString()}</td>
                  <td className="py-2 pr-2 font-mono text-white text-xs text-right">{m.material_length?.toLocaleString() || '-'}</td>
                  <td className="py-2 pr-2 font-mono text-white text-xs text-right font-semibold">{m.total_weight?.toLocaleString()}</td>
                  <td className="py-2 pr-2 text-center"><Badge variant={m.issued_for_info === 'Yes' ? 'success' : 'default'}>{m.issued_for_info}</Badge></td>
                  <td className="py-2 text-center"><Badge variant={m.issued_for_construction === 'Yes' ? 'success' : 'warning'}>{m.issued_for_construction}</Badge></td>
                  <td className="py-2">
                    <button
                      onClick={() => onDeleteMaterial(m.material_id, m.piece_mark || m.material_id)}
                      className="p-1 rounded hover:bg-red-900/40 text-slate-500 hover:text-red-400 transition-colors"
                      title={`Delete ${m.piece_mark || m.material_id}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={isPiping ? 16 : 15} className="py-6 text-center text-slate-500">
                {selectedDrawingId ? 'No materials found for this drawing' : 'No material data available'}
              </td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {/* Procurement Planning — only show per selected drawing */}
      {selectedDrawingId && planning.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Package className="h-4 w-4 text-amber-400" />
            Procurement Planning – Material Summary
            <span className="text-xs text-blue-400 font-normal ml-1">
              ({selectedDrawingNumber})
            </span>
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                  <th className="py-2 pr-2">{isPiping ? 'Material Cat' : 'Material Category'}</th>
                  <th className="py-2 pr-2">Material Type</th>
                  <th className="py-2 pr-2">{isPiping ? 'Pipe OD' : 'Size'}</th>
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
                {planning.map((p: any, idx: number) => (
                  <tr key={idx} className="border-b border-slate-800/50">
                    <td className="py-2.5 pr-2"><Badge variant={isPiping ? 'info' : 'warning'}>{p.material_category}</Badge></td>
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
                        const displayPoStatus = isPiping && p.po_status === 'Structure-requested'
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
            {isPiping ? (
              <p><span className="font-semibold text-slate-300">piping-requested:</span> Piping team requested to order</p>
            ) : (
              <p><span className="font-semibold text-slate-300">Structure-requested:</span> Structure team requested to order</p>
            )}
            <p><span className="font-semibold text-slate-300">PR-Raised:</span> Material confirmed and purchase order created</p>
          </div>
        </div>
      )}

    </div>
  );
}

/* ===== EQUIPMENT TABLE (Mechanical, Electrical, HVAC) ===== */
function EquipmentTable({ discipline, equipment, selectedDrawingId, selectedDrawingNumber, onClearFilter }: {
  discipline: string; equipment: any;
  selectedDrawingId: string | null; selectedDrawingNumber: string | null;
  onClearFilter: () => void;
}) {
  if (!equipment) return <div className="text-slate-400 py-6 text-center">Loading equipment data...</div>;
  const allItems = equipment.items || [];
  const planning = equipment.procurement_planning || [];

  const items = selectedDrawingId
    ? allItems.filter((e: any) => e.drawing_id === selectedDrawingId)
    : allItems;

  return (
    <div className="space-y-6">
      {/* Equipment Detail Table */}
      <div>
        <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Wrench className="h-4 w-4" />
          Equipment & Material Summary – {discipline}
        </h4>
        {/* Filter Banner */}
        {selectedDrawingId && selectedDrawingNumber && (
          <div className="flex items-center justify-between p-3 bg-blue-950/40 border border-blue-800/50 rounded-lg mb-3">
            <div className="flex items-center gap-2 text-sm">
              <FileText className="h-4 w-4 text-blue-400" />
              <span className="text-slate-300">Filtered to drawing:</span>
              <span className="font-mono font-semibold text-blue-300">{selectedDrawingNumber}</span>
              <span className="text-slate-500">({items.length} equipment item{items.length !== 1 ? 's' : ''})</span>
            </div>
            <button
              onClick={onClearFilter}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md border border-slate-600 text-slate-300 hover:text-white hover:border-slate-500 transition-colors"
            >
              <X className="h-3 w-3" /> Clear Filter
            </button>
          </div>
        )}
        {items.length === 0 ? (
          <div className="text-slate-500 py-6 text-center">No equipment data available</div>
        ) : (
          <div className="overflow-x-auto border border-slate-700/50 rounded-lg">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-700 bg-slate-900/40">
                  <th className="py-2 pr-2 pl-3 w-10">S/No</th>
                  <th className="py-2 pr-2 w-24">System Code</th>
                  <th className="py-2 pr-2 w-32">System Name</th>
                  <th className="py-2 pr-2 w-36">Equipment Name</th>
                  <th className="py-2 pr-2 w-44">Equipment Detail</th>
                  <th className="py-2 pr-2 w-28">Item Tag No</th>
                  <th className="py-2 pr-2 w-32">Shop Test Status</th>
                  <th className="py-2 pr-2 w-32">Testing Report / Certs</th>
                  <th className="py-2 pr-2 w-28">Schedule Deliver Date</th>
                  <th className="py-2 pr-2 w-28">Schedule Install Date</th>
                  <th className="py-2 pr-3 w-40">Remark</th>
                </tr>
              </thead>
              <tbody>
                {items.map((e: any, idx: number) => {
                  const isAfc = e.issued_for_construction === 'Yes';
                  const isAfi = e.issued_for_info === 'Yes' && !isAfc;
                  return (
                  <tr key={e.equipment_id} className={`border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors ${
                    isAfc ? 'bg-emerald-950/10' : isAfi ? 'bg-amber-950/10' : ''
                  }`}>
                    <td className="py-2.5 pr-2 pl-3 text-slate-500 text-xs">{idx + 1}</td>
                    <td className="py-2.5 pr-2 font-mono text-white text-xs">{e.system_code || '-'}</td>
                    <td className="py-2.5 pr-2 text-slate-300 text-xs">{e.system_name || '-'}</td>
                    <td className="py-2.5 pr-2 text-slate-300 text-xs font-medium">{e.equipment_name || '-'}</td>
                    <td className="py-2.5 pr-2 text-slate-400 text-xs max-w-44 truncate" title={e.equipment_detail}>{e.equipment_detail || '-'}</td>
                    <td className="py-2.5 pr-2 font-mono text-white text-xs">{e.equipment_tag}</td>
                    <td className="py-2.5 pr-2">
                      <div className="flex flex-col gap-0.5">
                        {e.fat_status === 'APPROVED' ? (
                          <Badge variant="success">FAT: Approved</Badge>
                        ) : e.fat_status === 'SUBMITTED' ? (
                          <Badge variant="info">FAT: Submitted</Badge>
                        ) : (
                          <Badge variant="warning">FAT: Pending</Badge>
                        )}
                        {e.test_status && (
                          <span className={`text-xs font-mono ${
                            e.test_status.toLowerCase().includes('pass') ? 'text-emerald-400' :
                            e.test_status.toLowerCase().includes('pending') ? 'text-amber-400' :
                            'text-slate-400'
                          }`}>{e.test_status}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 pr-2 text-slate-400 text-xs">{e.certification || '-'}</td>
                    <td className="py-2.5 pr-2 text-slate-300 text-xs">{e.schedule_delivery_date || '-'}</td>
                    <td className="py-2.5 pr-2 text-slate-300 text-xs">{e.schedule_install_date || '-'}</td>
                    <td className="py-2.5 pr-3 text-slate-500 text-xs max-w-40 truncate" title={e.remark}>{e.remark || '-'}</td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Procurement Planning Summary */}
      {planning.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
            <Package className="h-4 w-4 text-amber-400" />
            Procurement Planning – Equipment Type Summary
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="text-left text-xs text-slate-400 border-b border-slate-700">
                  <th className="py-2 pr-3">Equipment Type</th>
                  <th className="py-2 pr-3 text-center">Count</th>
                  <th className="py-2 pr-3 text-right">Total Weight (kg)</th>
                  <th className="py-2 pr-3 text-center">FAT Approved</th>
                  <th className="py-2 text-center">FAT Pending</th>
                </tr>
              </thead>
              <tbody>
                {planning.map((p: any) => (
                  <tr key={p.equipment_type} className="border-b border-slate-800/50">
                    <td className="py-2.5 pr-3"><Badge variant="warning">{p.equipment_type}</Badge></td>
                    <td className="py-2.5 pr-3 text-center font-mono text-white">{p.count}</td>
                    <td className="py-2.5 pr-3 font-mono text-right text-white font-semibold">{p.total_weight_kg?.toLocaleString()}</td>
                    <td className="py-2.5 pr-3 text-center"><Badge variant="success">{p.fat_approved}</Badge></td>
                    <td className="py-2.5 text-center"><Badge variant={p.fat_pending > 0 ? 'warning' : 'default'}>{p.fat_pending}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/* ===== CHANGE SUMMARY PANEL ===== */
function ChangeSummaryPanel({ summary }: { summary: ChangeSummary }) {
  const totalDrawings = summary.drawings_added + summary.drawings_deleted;
  const totalMaterials = summary.materials_added + summary.materials_deleted;
  if (totalDrawings === 0 && totalMaterials === 0) return null;

  return (
    <Card className="border border-slate-700/50 bg-slate-800/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <BarChart3 className="h-4 w-4" /> Project Change Tracking
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400">Drawings</p>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-emerald-400 font-mono">+{summary.drawings_added}</span>
              <span className="text-slate-500">added</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-red-400 font-mono">-{summary.drawings_deleted}</span>
              <span className="text-slate-500">deleted</span>
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-xs font-semibold text-slate-400">Materials</p>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-emerald-400 font-mono">+{summary.materials_added}</span>
              <span className="text-slate-500">added</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-red-400 font-mono">-{summary.materials_deleted}</span>
              <span className="text-slate-500">deleted</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
