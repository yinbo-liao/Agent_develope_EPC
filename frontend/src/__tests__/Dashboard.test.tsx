import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Mock all child components to isolate Dashboard navigation testing
vi.mock('../components/engineering/DisciplineDeliverables', () => ({
  DisciplineDeliverables: () => <div data-testid="eng-component">Engineering</div>,
}));
vi.mock('../components/procurement/PurchaseOrderTracker', () => ({
  PurchaseOrderTracker: () => <div data-testid="proc-component">Procurement</div>,
}));
vi.mock('../components/construction/WeeklyPlanner', () => ({
  WeeklyPlanner: () => <div data-testid="const-component">Construction</div>,
}));
vi.mock('../components/construction/ConstructionMaterialTracker', () => ({
  ConstructionMaterialTracker: () => <div data-testid="const-mat-component">Materials</div>,
}));
vi.mock('../components/inspection/NDTProgressChart', () => ({
  NDTProgressChart: () => <div data-testid="ndt-component">NDT</div>,
}));
vi.mock('../components/reports/AccountabilityReport', () => ({
  AccountabilityReport: () => <div data-testid="report-component">Reports</div>,
}));
vi.mock('../components/planning/PlanningBoard', () => ({
  PlanningBoard: () => <div data-testid="planning-component">Planning</div>,
}));
vi.mock('../components/completion/SubSystemProgress', () => ({
  SubSystemProgress: () => <div data-testid="completion-component">Completion</div>,
}));
vi.mock('../components/completion/PunchListTracker', () => ({
  PunchListTracker: () => <div data-testid="punch-component">Punch List</div>,
}));
vi.mock('../components/commissioning/CommissioningDashboard', () => ({
  CommissioningDashboard: () => <div data-testid="commissioning-component">Commissioning</div>,
}));
vi.mock('../components/quality/NCRDashboard', () => ({
  NCRDashboard: () => <div data-testid="ncr-component">NCR</div>,
}));
vi.mock('../components/quality/WeldRejectionAnalytics', () => ({
  WeldRejectionAnalytics: () => <div data-testid="weld-component">Weld</div>,
}));
vi.mock('../components/safety/SafetyDashboard', () => ({
  SafetyDashboard: () => <div data-testid="safety-component">Safety</div>,
}));
vi.mock('../components/training/TrainingMatrix', () => ({
  TrainingMatrix: () => <div data-testid="training-component">Training</div>,
}));
vi.mock('../components/stagegate/StageGateControl', () => ({
  StageGateControl: () => <div data-testid="stagegate-component">Stage Gates</div>,
}));
vi.mock('../components/ai/AIInsightPanel', () => ({
  AIInsightPanel: () => <div data-testid="ai-component">AI Insights</div>,
}));
vi.mock('../components/conflict/ConflictResolutionBoard', () => ({
  ConflictResolutionBoard: () => <div data-testid="conflict-component">Conflicts</div>,
}));
vi.mock('../components/feedback/FeedbackLoopDashboard', () => ({
  FeedbackLoopDashboard: () => <div data-testid="feedback-component">Feedback</div>,
}));
vi.mock('../components/integration/TraceabilityChain', () => ({
  TraceabilityChain: () => <div data-testid="traceability-component">Traceability</div>,
}));
vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => {},
}));

// Mock apiClient
vi.mock('../lib/api-client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      data: {
        project: {
          project_id: 'test-project', project_code: 'FPSO-TEST',
          project_name: 'Test FPSO', client_name: 'Test Client',
          planned_start_date: '2025-01-01', planned_finish_date: '2028-12-31',
          contract_value: 1000000000, current_status: 'ACTIVE',
        },
        activities: { total: 10, critical_count: 3, avg_progress: 45 },
        alerts: [],
      },
    }),
  },
}));

import { Dashboard } from '../pages/Dashboard';

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/test-project']}>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Dashboard Navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the sidebar header', () => {
    renderWithProviders();
    // Sidebar header renders "FPSO EPC" and "Project Control" as separate text nodes
    const fpsoTexts = screen.getAllByText(/FPSO/i);
    expect(fpsoTexts.length).toBeGreaterThan(0);
    const controlTexts = screen.getAllByText(/Project Control/i);
    expect(controlTexts.length).toBeGreaterThan(0);
  });

  it('renders all 17 navigation items', () => {
    renderWithProviders();
    const navItems = [
      'Planning Board', 'Engineering', 'Procurement',
      'Construction', 'System Completion', 'Commissioning',
      'Inspection & NDT', 'Quality (NCR)', 'HSE Safety', 'Training',
      'Stage Gates', 'Conflicts', 'Feedback Loop', 'Traceability',
      'AI Insights', 'Reports',
    ];
    for (const item of navItems) {
      expect(screen.getByText(item)).toBeTruthy();
    }
    // Overview appears twice (sidebar + header), use getAllByText
    const overviewEls = screen.getAllByText('Overview');
    expect(overviewEls.length).toBeGreaterThanOrEqual(1);
  });

  it('shows KPI cards on overview by default', () => {
    renderWithProviders();
    expect(screen.getByText('Activities')).toBeTruthy();
    expect(screen.getByText('Avg. Progress')).toBeTruthy();
    expect(screen.getByText('Open Alerts')).toBeTruthy();
    expect(screen.getByText('Contract Value')).toBeTruthy();
  });

  it('renders overview section by default', () => {
    renderWithProviders();
    expect(screen.getByText('Project Overview')).toBeTruthy();
  });
});
