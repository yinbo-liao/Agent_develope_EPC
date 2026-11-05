import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Mock apiClient globally for all component tests
vi.mock('../lib/api-client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    post: vi.fn().mockResolvedValue({ data: { status: 'ok' } }),
    patch: vi.fn().mockResolvedValue({ data: { status: 'updated' } }),
  },
}));

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>
  );
}

// Test UI primitives exist and render
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Progress } from '../components/ui/Progress';
import { Button } from '../components/ui/Button';

describe('UI Primitives', () => {
  describe('Card', () => {
    it('renders card with content', () => {
      const { container } = render(
        <Card>
          <CardHeader><CardTitle>Test Card</CardTitle></CardHeader>
          <CardContent>Content here</CardContent>
        </Card>
      );
      expect(screen.getByText('Test Card')).toBeTruthy();
      expect(screen.getByText('Content here')).toBeTruthy();
    });

    it('applies dark theme classes', () => {
      const { container } = render(<Card><CardContent>test</CardContent></Card>);
      const card = container.firstChild as HTMLElement;
      expect(card.className).toContain('bg-slate');
    });
  });

  describe('Badge', () => {
    it('renders with default variant', () => {
      render(<Badge>Default</Badge>);
      expect(screen.getByText('Default')).toBeTruthy();
    });

    it('renders with destructive variant (red colors)', () => {
      render(<Badge variant="destructive">Error</Badge>);
      const badge = screen.getByText('Error');
      expect(badge.className).toContain('bg-red');
      expect(badge.className).toContain('text-red');
    });

    it('renders with success variant (emerald colors)', () => {
      render(<Badge variant="success">OK</Badge>);
      const badge = screen.getByText('OK');
      expect(badge.className).toContain('bg-emerald');
      expect(badge.className).toContain('text-emerald');
    });

    it('renders with warning variant (amber colors)', () => {
      render(<Badge variant="warning">Warn</Badge>);
      const badge = screen.getByText('Warn');
      expect(badge.className).toContain('bg-amber');
      expect(badge.className).toContain('text-amber');
    });
  });

  describe('Progress', () => {
    it('renders progress bar with value', () => {
      const { container } = render(<Progress value={75} />);
      const progressBar = container.firstChild as HTMLElement;
      expect(progressBar).toBeTruthy();
    });

    it('accepts custom className', () => {
      const { container } = render(<Progress value={50} className="h-2" />);
      const el = container.firstChild as HTMLElement;
      expect(el.className).toContain('h-2');
    });
  });

  describe('Button', () => {
    it('renders button with text', () => {
      render(<Button>Click Me</Button>);
      expect(screen.getByText('Click Me')).toBeTruthy();
    });

    it('accepts custom className', () => {
      render(<Button className="custom-btn">Styled</Button>);
      const btn = screen.getByText('Styled');
      expect(btn.className).toContain('custom-btn');
    });
  });
});

// Test PlanningBoard renders period type tabs
import { PlanningBoard } from '../components/planning/PlanningBoard';
import { MemoryRouter } from 'react-router-dom';

describe('PlanningBoard', () => {
  it('renders period type tabs', () => {
    renderWithQuery(
      <MemoryRouter>
        <PlanningBoard projectId="test-project" />
      </MemoryRouter>
    );
    expect(screen.getByText('Multi-Level Planning Board')).toBeTruthy();
    expect(screen.getByText('Weekly')).toBeTruthy();
    expect(screen.getByText('Bi-Weekly')).toBeTruthy();
    expect(screen.getByText('Monthly')).toBeTruthy();
    expect(screen.getByText('Bi-Monthly')).toBeTruthy();
    expect(screen.getByText('4-Month')).toBeTruthy();
    expect(screen.getByText('Generate Plans')).toBeTruthy();
  });
});

// Test NCRDashboard renders severity filters
import { NCRDashboard } from '../components/quality/NCRDashboard';

describe('NCRDashboard', () => {
  it('renders header and severity labels', () => {
    renderWithQuery(
      <MemoryRouter>
        <NCRDashboard projectId="test-project" />
      </MemoryRouter>
    );
    expect(screen.getByText('NCR Dashboard')).toBeTruthy();
    expect(screen.getByText('NCR Aging (Open)')).toBeTruthy();
    expect(screen.getByText('By Discipline')).toBeTruthy();
  });
});

// Test SafetyDashboard renders HSE KPIs
import { SafetyDashboard } from '../components/safety/SafetyDashboard';

describe('SafetyDashboard', () => {
  it('renders HSE KPI labels', () => {
    renderWithQuery(
      <MemoryRouter>
        <SafetyDashboard projectId="test-project" />
      </MemoryRouter>
    );
    expect(screen.getByText('Safety (HSE) Dashboard')).toBeTruthy();
    expect(screen.getByText('TRIR')).toBeTruthy();
    expect(screen.getByText('LTIFR')).toBeTruthy();
    expect(screen.getByText('Safe Man-Hours')).toBeTruthy();
    expect(screen.getByText('LTI Count')).toBeTruthy();
  });
});
