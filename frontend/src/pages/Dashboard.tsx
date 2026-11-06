import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { DisciplineDeliverables } from '../components/engineering/DisciplineDeliverables';
import { PurchaseOrderTracker } from '../components/procurement/PurchaseOrderTracker';
import { WeeklyPlanner } from '../components/construction/WeeklyPlanner';
import { ConstructionMaterialTracker } from '../components/construction/ConstructionMaterialTracker';
import { NDTProgressChart } from '../components/inspection/NDTProgressChart';
import { AccountabilityReport } from '../components/reports/AccountabilityReport';
import { PlanningBoard } from '../components/planning/PlanningBoard';
import { SubSystemProgress } from '../components/completion/SubSystemProgress';
import { PunchListTracker } from '../components/completion/PunchListTracker';
import { CommissioningDashboard } from '../components/commissioning/CommissioningDashboard';
import { NCRDashboard } from '../components/quality/NCRDashboard';
import { WeldRejectionAnalytics } from '../components/quality/WeldRejectionAnalytics';
import { SafetyDashboard } from '../components/safety/SafetyDashboard';
import { TrainingMatrix } from '../components/training/TrainingMatrix';
import { StageGateControl } from '../components/stagegate/StageGateControl';
import { AIInsightPanel } from '../components/ai/AIInsightPanel';
import { ConflictResolutionBoard } from '../components/conflict/ConflictResolutionBoard';
import { FeedbackLoopDashboard } from '../components/feedback/FeedbackLoopDashboard';
import { TraceabilityChain } from '../components/integration/TraceabilityChain';
import { useWebSocket } from '../hooks/useWebSocket';
import { apiClient } from '../lib/api-client';
import { useOptionalAuth } from '../auth/context';
import {
  Activity, BarChart3, AlertTriangle, Wrench, Home, FileText,
  ShoppingCart, HardHat, ClipboardCheck, FileBarChart, Menu, X,
  Calendar, Layers, Zap, Shield, Siren, GraduationCap, DoorOpen,
  Brain, MessageSquare, Link, LogOut,
} from 'lucide-react';

const NAV_ITEMS = [
  { value: 'overview', label: 'Overview', icon: Home },
  { value: 'planning', label: 'Planning Board', icon: Calendar },
  { value: 'engineering', label: 'Engineering', icon: FileText },
  { value: 'procurement', label: 'Procurement', icon: ShoppingCart },
  { value: 'construction', label: 'Construction', icon: HardHat },
  { value: 'completion', label: 'System Completion', icon: Layers },
  { value: 'commissioning', label: 'Commissioning', icon: Zap },
  { value: 'inspection', label: 'Inspection & NDT', icon: ClipboardCheck },
  { value: 'quality', label: 'Quality (NCR)', icon: Shield },
  { value: 'safety', label: 'HSE Safety', icon: Siren },
  { value: 'training', label: 'Training', icon: GraduationCap },
  { value: 'stagegates', label: 'Stage Gates', icon: DoorOpen },
  { value: 'conflicts', label: 'Conflicts', icon: AlertTriangle },
  { value: 'feedback', label: 'Feedback Loop', icon: MessageSquare },
  { value: 'traceability', label: 'Traceability', icon: Link },
  { value: 'ai', label: 'AI Insights', icon: Brain },
  { value: 'reports', label: 'Reports', icon: FileBarChart },
];

export function Dashboard() {
  const { projectId } = useParams<{ projectId: string }>();
  const [activeNav, setActiveNav] = useState('overview');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const auth = useOptionalAuth();
  const today = new Date();
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - today.getDay());
  const weekEnd = new Date(today);

  const { data: dashData } = useQuery({
    queryKey: ['dashboard', projectId],
    queryFn: () => apiClient.get(`/api/reports/dashboard/${projectId}`),
    refetchInterval: 15000,
  });
  const { data: alertsData } = useQuery({
    queryKey: ['alerts', projectId],
    queryFn: () => apiClient.get(`/api/alerts/${projectId}`),
    refetchInterval: 15000,
  });

  useWebSocket(projectId, (msg) => {
    const data = msg as { type?: string };
    console.log('[WS]', data.type);
  });

  const project = dashData?.data?.project;
  const activities = dashData?.data?.activities;
  const alerts = alertsData?.data || [];

  useEffect(() => {
    document.title = project?.project_name
      ? `${project.project_name} — FPSO Project Control`
      : 'FPSO EPC Project Control';
  }, [project?.project_name]);

  const user = auth?.user;
  const displayName = user?.full_name || user?.username || '';
  const roleLabel = user?.role ? user.role.replace(/_/g, ' ') : '';

  return (
    <div className="min-h-screen bg-slate-950 flex">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Left Sidebar */}
      <aside className={`
        fixed lg:sticky top-0 left-0 z-50 h-screen w-56 bg-slate-900 border-r border-slate-800
        flex flex-col transition-transform duration-200
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        {/* Sidebar Header */}
        <div className="px-5 py-4 border-b border-slate-800">
          <h1 className="text-sm font-bold text-white tracking-tight leading-tight">
            FPSO EPC<br />Project Control
          </h1>
          {project && (
            <p className="text-[10px] text-slate-500 mt-1 truncate">{project.project_code}</p>
          )}
        </div>

        {/* Nav Items */}
        <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const isActive = activeNav === item.value;
            const Icon = item.icon;
            return (
              <button
                key={item.value}
                onClick={() => { setActiveNav(item.value); setSidebarOpen(false); }}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-xs font-medium rounded-lg transition-all duration-150 ${
                  isActive
                    ? 'bg-primary/20 text-white border-l-2 border-primary shadow-sm'
                    : 'text-slate-400 hover:text-white hover:bg-slate-800/60 border-l-2 border-transparent'
                }`}
              >
                <Icon className={`h-4 w-4 shrink-0 ${isActive ? 'text-primary' : 'text-slate-500'}`} />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Sidebar Footer */}
        <div className="px-5 py-3 border-t border-slate-800 text-[10px] text-slate-600">
          {project?.current_status === 'ACTIVE' ? '● Active' : '● ' + (project?.current_status || 'N/A')}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Bar */}
        <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-30">
          <div className="px-4 lg:px-6 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-1.5 rounded-md text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              >
                {sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
              <div>
                <h2 className="text-sm font-semibold text-white">
                  {NAV_ITEMS.find((n) => n.value === activeNav)?.label || 'Dashboard'}
                </h2>
                {project && <p className="text-xs text-slate-500">{project.project_name}</p>}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {alerts.some((a: any) => a.severity === 'CRITICAL') && (
                <Badge variant="destructive" className="animate-pulse text-[10px]">
                  <AlertTriangle className="h-3 w-3 mr-1" /> Critical
                </Badge>
              )}
              <Badge variant={project?.current_status === 'ACTIVE' ? 'success' : 'warning'} className="text-[10px]">
                {project?.current_status || 'N/A'}
              </Badge>
              {user && (
                <div className="flex items-center gap-2 pl-2 ml-1 border-l border-slate-800">
                  <div className="hidden sm:block text-right max-w-[160px]">
                    <p className="text-xs font-medium text-white truncate">{displayName}</p>
                    <p className="text-[10px] text-slate-400 uppercase tracking-wide truncate">{roleLabel}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => { void auth?.logout(); }}
                    aria-label="Log out"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-light focus-visible:ring-offset-2 focus-visible:ring-offset-slate-900"
                  >
                    <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
                    <span className="hidden lg:inline">Log out</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 px-4 lg:px-6 py-5 overflow-x-hidden">
          {/* KPI Cards */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mb-5">
            <Card>
              <CardContent className="flex items-center gap-3 py-3">
                <Activity className="h-7 w-7 text-blue-400 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">Activities</p>
                  <p className="text-xl font-bold">{activities?.total || 0}</p>
                  <p className="text-[10px] text-amber-400">{activities?.critical_count || 0} critical</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3 py-3">
                <BarChart3 className="h-7 w-7 text-emerald-400 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">Avg. Progress</p>
                  <p className="text-xl font-bold">{activities?.avg_progress || 0}%</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3 py-3">
                <AlertTriangle className="h-7 w-7 text-red-400 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">Open Alerts</p>
                  <p className="text-xl font-bold">{Array.isArray(alerts) ? alerts.length : 0}</p>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="flex items-center gap-3 py-3">
                <Wrench className="h-7 w-7 text-purple-400 shrink-0" />
                <div>
                  <p className="text-[10px] text-slate-400 uppercase tracking-wide">Contract Value</p>
                  <p className="text-lg font-bold">{project?.contract_value ? `$${(+project.contract_value / 1e6).toFixed(1)}M` : 'N/A'}</p>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Active Section Content */}
          {activeNav === 'overview' && (
            <div className="space-y-5">
              <Card>
                <CardHeader><CardTitle>Project Overview</CardTitle></CardHeader>
                <CardContent>
                  {project && (
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                      <div><span className="text-slate-400">Client</span><p className="font-semibold">{project.client_name || 'N/A'}</p></div>
                      <div><span className="text-slate-400">Planned Start</span><p className="font-semibold">{project.planned_start_date}</p></div>
                      <div><span className="text-slate-400">Planned Finish</span><p className="font-semibold">{project.planned_finish_date}</p></div>
                      <div><span className="text-slate-400">Baseline Finish</span><p className="font-semibold">{project.baseline_finish_date || 'Not set'}</p></div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {alerts.length > 0 && (
                <Card className="border-l-4 border-l-red-500">
                  <CardHeader><CardTitle className="text-red-400">Active Alerts ({alerts.length})</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    {alerts.slice(0, 5).map((a: any) => (
                      <div key={a.alert_id} className="flex items-start gap-2 p-2 bg-slate-900/60 rounded">
                        <Badge variant={a.severity === 'CRITICAL' ? 'destructive' : a.severity === 'HIGH' ? 'warning' : 'default'}>{a.severity}</Badge>
                        <div><p className="text-sm">{a.alert_title}</p><p className="text-xs text-slate-500">{a.recommended_action}</p></div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {activeNav === 'engineering' && <DisciplineDeliverables projectId={projectId!} />}
          {activeNav === 'procurement' && <PurchaseOrderTracker projectId={projectId!} />}
          {activeNav === 'construction' && (
            <div className="space-y-6">
              <ConstructionMaterialTracker projectId={projectId!} />
              <WeeklyPlanner projectId={projectId!} weekStart={weekStart} />
            </div>
          )}
          {activeNav === 'planning' && <PlanningBoard projectId={projectId!} />}
          {activeNav === 'completion' && (
            <div className="space-y-6">
              <SubSystemProgress projectId={projectId!} />
              <PunchListTracker projectId={projectId!} />
            </div>
          )}
          {activeNav === 'commissioning' && <CommissioningDashboard projectId={projectId!} />}
          {activeNav === 'quality' && (
            <div className="space-y-6">
              <NCRDashboard projectId={projectId!} />
              <WeldRejectionAnalytics projectId={projectId!} />
            </div>
          )}
          {activeNav === 'safety' && <SafetyDashboard projectId={projectId!} />}
          {activeNav === 'training' && <TrainingMatrix projectId={projectId!} />}
          {activeNav === 'stagegates' && <StageGateControl projectId={projectId!} />}
          {activeNav === 'conflicts' && <ConflictResolutionBoard projectId={projectId!} />}
          {activeNav === 'feedback' && <FeedbackLoopDashboard projectId={projectId!} />}
          {activeNav === 'traceability' && <TraceabilityChain projectId={projectId!} />}
          {activeNav === 'ai' && <AIInsightPanel projectId={projectId!} />}
          {activeNav === 'inspection' && <NDTProgressChart projectId={projectId!} />}
          {activeNav === 'reports' && <AccountabilityReport projectId={projectId!} weekEnding={weekEnd} />}
        </main>
      </div>
    </div>
  );
}
