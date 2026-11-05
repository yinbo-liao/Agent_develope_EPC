import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../ui/Card';
import { Badge } from '../ui/Badge';
import { Progress } from '../ui/Progress';
import { Button } from '../ui/Button';
import { apiClient } from '../../lib/api-client';
import { Link, ArrowRight, ArrowLeft, Search, AlertTriangle, FileText, ShoppingCart, Wrench, ClipboardCheck, Zap } from 'lucide-react';

const PHASE_ICONS: Record<string, any> = {
  engineering: FileText,
  mto: FileText,
  procurement: ShoppingCart,
  inspection: ClipboardCheck,
};

const STATUS_COLORS: Record<string, string> = {
  COMPLETE: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
  IN_PROGRESS: 'bg-blue-500/10 text-blue-400 border-blue-500/30',
  PENDING: 'bg-slate-500/10 text-slate-400 border-slate-500/30',
};

export function TraceabilityChain({ projectId }: { projectId: string }) {
  const [traceMode, setTraceMode] = useState<'forward' | 'backward'>('forward');
  const [drawingId, setDrawingId] = useState('');
  const [systemCode, setSystemCode] = useState('');
  const [entityType, setEntityType] = useState('drawing');
  const [entityId, setEntityId] = useState('');

  // Traceability Matrix
  const { data: matrix, isLoading: matrixLoading } = useQuery({
    queryKey: ['traceability-matrix', projectId],
    queryFn: () => apiClient.get(`/api/traceability/matrix/${projectId}`),
    refetchInterval: 60000,
  });

  const matrixData = matrix?.data || [];

  // Stats from matrix
  const totalDrawings = matrixData.length;
  const ifcCount = matrixData.filter((d: any) => d.ifc === 'Yes').length;
  const withNDT = matrixData.filter((d: any) => d.ndt_count > 0).length;
  const withMaterials = matrixData.filter((d: any) => d.material_count > 0).length;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <Link className="h-5 w-5 text-cyan-400" />
        <h3 className="text-lg font-semibold text-white">Traceability Matrix</h3>
      </div>

      {/* KPI Cards */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">Total Drawings</p>
            <p className="text-xl font-bold">{totalDrawings}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">IFC Issued</p>
            <p className="text-xl font-bold text-emerald-400">{ifcCount}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">With Materials</p>
            <p className="text-xl font-bold text-blue-400">{withMaterials}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-3 text-center">
            <p className="text-[10px] text-slate-400 uppercase tracking-wide">With NDT</p>
            <p className="text-xl font-bold text-purple-400">{withNDT}</p>
          </CardContent>
        </Card>
      </div>

      {/* Trace Mode Selector */}
      <div className="flex gap-2 bg-slate-900 rounded-lg p-1 w-fit">
        <button
          onClick={() => setTraceMode('forward')}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5 ${
            traceMode === 'forward' ? 'bg-primary/20 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          <ArrowRight className="h-3.5 w-3.5" /> Forward Trace
        </button>
        <button
          onClick={() => setTraceMode('backward')}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all flex items-center gap-1.5 ${
            traceMode === 'backward' ? 'bg-primary/20 text-white' : 'text-slate-400 hover:text-white'
          }`}
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Backward Trace
        </button>
      </div>

      {/* Trace Input */}
      <Card>
        <CardContent className="py-3">
          <div className="flex items-end gap-3 flex-wrap">
            {traceMode === 'forward' ? (
              <>
                <div className="flex-1 min-w-[200px]">
                  <label className="text-[10px] text-slate-500 block mb-1">Drawing ID</label>
                  <input
                    type="text"
                    value={drawingId}
                    onChange={e => setDrawingId(e.target.value)}
                    placeholder="Enter drawing UUID..."
                    className="w-full px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white placeholder:text-slate-600 focus:outline-none focus:border-primary"
                  />
                </div>
                <Button onClick={() => {
                  if (drawingId) window.open(`/api/traceability/forward/${projectId}/${drawingId}`, '_blank');
                }} className="text-xs" disabled={!drawingId}>
                  <Search className="h-3.5 w-3.5 mr-1" /> Trace Forward
                </Button>
              </>
            ) : (
              <>
                <div className="flex-1 min-w-[200px]">
                  <label className="text-[10px] text-slate-500 block mb-1">System Code</label>
                  <input
                    type="text"
                    value={systemCode}
                    onChange={e => setSystemCode(e.target.value)}
                    placeholder="e.g. SYS-001"
                    className="w-full px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white placeholder:text-slate-600 focus:outline-none focus:border-primary"
                  />
                </div>
                <Button onClick={() => {
                  if (systemCode) window.open(`/api/traceability/backward/${projectId}/${systemCode}`, '_blank');
                }} className="text-xs" disabled={!systemCode}>
                  <Search className="h-3.5 w-3.5 mr-1" /> Trace Backward
                </Button>
              </>
            )}
          </div>

          {/* Impact Analysis */}
          <div className="flex items-end gap-3 mt-3 pt-3 border-t border-slate-800">
            <select
              value={entityType}
              onChange={e => setEntityType(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white focus:outline-none focus:border-primary"
            >
              <option value="drawing">Drawing</option>
              <option value="activity">Activity</option>
              <option value="purchase_order">Purchase Order</option>
              <option value="equipment">Equipment</option>
            </select>
            <input
              type="text"
              value={entityId}
              onChange={e => setEntityId(e.target.value)}
              placeholder="Entity UUID..."
              className="flex-1 px-3 py-1.5 text-xs bg-slate-800 border border-slate-700 rounded-md text-white placeholder:text-slate-600 focus:outline-none focus:border-primary"
            />
            <Button onClick={() => {
              if (entityId) window.open(`/api/traceability/impact/${projectId}?entity_type=${entityType}&entity_id=${entityId}`, '_blank');
            }} className="text-xs" disabled={!entityId}>
              <AlertTriangle className="h-3.5 w-3.5 mr-1" /> Impact Analysis
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Full Matrix Table */}
      {matrixLoading ? (
        <div className="text-center py-10 text-slate-500">Loading traceability matrix...</div>
      ) : (
        <Card>
          <CardHeader><CardTitle className="text-sm">Full Traceability Matrix ({matrixData.length} drawings)</CardTitle></CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-slate-900">
                  <tr className="text-slate-500 border-b border-slate-800">
                    <th className="text-left py-2 px-3 font-medium">Drawing #</th>
                    <th className="text-left py-2 px-3 font-medium">Title</th>
                    <th className="text-left py-2 px-3 font-medium">Discipline</th>
                    <th className="text-center py-2 px-3 font-medium">Status</th>
                    <th className="text-center py-2 px-3 font-medium">IFC</th>
                    <th className="text-center py-2 px-3 font-medium">Materials</th>
                    <th className="text-center py-2 px-3 font-medium">Equipment</th>
                    <th className="text-center py-2 px-3 font-medium">PO Items</th>
                    <th className="text-center py-2 px-3 font-medium">NDT</th>
                    <th className="text-center py-2 px-3 font-medium">Welds</th>
                    <th className="text-center py-2 px-3 font-medium">Avg NDT %</th>
                  </tr>
                </thead>
                <tbody>
                  {matrixData.map((d: any) => (
                    <tr key={d.drawing_id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-2 px-3 font-mono text-slate-300">{d.drawing_number}</td>
                      <td className="py-2 px-3 text-slate-300 max-w-[180px] truncate" title={d.drawing_title}>{d.drawing_title}</td>
                      <td className="py-2 px-3 text-slate-400">{d.discipline_name}</td>
                      <td className="py-2 px-3 text-center">
                        <Badge variant={d.drawing_status === 'IFC' ? 'success' : 'default'}>{d.drawing_status}</Badge>
                      </td>
                      <td className="py-2 px-3 text-center">
                        {d.ifc === 'Yes'
                          ? <Badge variant="success">IFC</Badge>
                          : <span className="text-slate-500">—</span>
                        }
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={d.material_count > 0 ? 'text-white font-semibold' : 'text-slate-600'}>
                          {d.material_count || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={d.equipment_count > 0 ? 'text-white font-semibold' : 'text-slate-600'}>
                          {d.equipment_count || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={d.po_item_count > 0 ? 'text-white font-semibold' : 'text-slate-600'}>
                          {d.po_item_count || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={d.ndt_count > 0 ? 'text-purple-400 font-semibold' : 'text-slate-600'}>
                          {d.ndt_count || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={d.weld_count > 0 ? 'text-orange-400 font-semibold' : 'text-slate-600'}>
                          {d.weld_count || 0}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-center">
                        {d.avg_ndt_pct != null ? (
                          <div className="flex items-center gap-1 justify-center">
                            <Progress value={parseFloat(d.avg_ndt_pct)} className="w-10 h-1.5" />
                            <span className="text-[10px]">{Math.round(parseFloat(d.avg_ndt_pct))}%</span>
                          </div>
                        ) : (
                          <span className="text-slate-600">—</span>
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
