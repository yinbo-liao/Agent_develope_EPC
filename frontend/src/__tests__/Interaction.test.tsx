/** Interaction tests for UI primitives and common workflows. */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { ErrorBanner } from '../components/ui/ErrorBanner';
import { ConfirmDialog } from '../components/ui/ConfirmDialog';

describe('Tabs', () => {
  it('renders tab triggers with correct ARIA roles', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2">Content 2</TabsContent>
      </Tabs>
    );

    const tab1 = screen.getByRole('tab', { name: 'Tab 1' });
    const tab2 = screen.getByRole('tab', { name: 'Tab 2' });
    expect(tab1).toBeTruthy();
    expect(tab2).toBeTruthy();
    expect(tab1.getAttribute('aria-selected')).toBe('true');
    expect(tab2.getAttribute('aria-selected')).toBe('false');
  });

  it('switches tab content on click', async () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2">Content 2</TabsContent>
      </Tabs>
    );

    expect(screen.getByRole('tabpanel')).toHaveTextContent('Content 1');

    await userEvent.click(screen.getByRole('tab', { name: 'Tab 2' }));
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Content 2');
    expect(screen.getByRole('tab', { name: 'Tab 2' }).getAttribute('aria-selected')).toBe('true');
  });

  it('supports arrow key navigation', async () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2">Content 2</TabsContent>
      </Tabs>
    );

    const tab1 = screen.getByRole('tab', { name: 'Tab 1' });
    tab1.focus();
    expect(document.activeElement).toBe(tab1);

    fireEvent.keyDown(tab1, { key: 'ArrowRight' });
    // Focus should move to tab2
    const tab2 = screen.getByRole('tab', { name: 'Tab 2' });
    expect(document.activeElement).toBe(tab2);
  });
});

describe('Button', () => {
  it('defaults to type="button"', () => {
    render(<Button>Click Me</Button>);
    const btn = screen.getByRole('button', { name: 'Click Me' });
    expect(btn.getAttribute('type')).toBe('button');
  });

  it('fires onClick handler', async () => {
    let clicked = false;
    render(<Button onClick={() => { clicked = true; }}>Click</Button>);
    await userEvent.click(screen.getByRole('button', { name: 'Click' }));
    expect(clicked).toBe(true);
  });

  it('supports disabled state', () => {
    render(<Button disabled>Disabled</Button>);
    const btn = screen.getByRole('button', { name: 'Disabled' });
    expect(btn.hasAttribute('disabled')).toBe(true);
    expect(btn.getAttribute('aria-disabled')).toBe('true');
  });
});

describe('Badge', () => {
  it('renders with variant classes', () => {
    const { container } = render(<Badge variant="success">Done</Badge>);
    const badge = container.querySelector('span');
    expect(badge?.className).toContain('bg-emerald');
  });

  it('defaults to default variant', () => {
    const { container } = render(<Badge>Default</Badge>);
    const badge = container.querySelector('span');
    expect(badge?.className).toContain('bg-slate-700');
  });
});

describe('ErrorBanner', () => {
  it('renders error message and retry button', async () => {
    let retried = false;
    render(
      <ErrorBanner
        title="Test Error"
        message="Something failed"
        onRetry={() => { retried = true; }}
      />
    );

    expect(screen.getByText('Test Error')).toBeTruthy();
    expect(screen.getByText('Something failed')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: /Retry/i }));
    expect(retried).toBe(true);
  });
});

describe('ConfirmDialog', () => {
  it('renders when open and calls onConfirm', async () => {
    let confirmed = false;
    let closed = false;

    render(
      <ConfirmDialog
        open={true}
        onClose={() => { closed = true; }}
        onConfirm={() => { confirmed = true; }}
        title="Delete Item"
        message="Are you sure?"
        variant="danger"
      />
    );

    expect(screen.getByRole('alertdialog')).toBeTruthy();
    expect(screen.getByText('Delete Item')).toBeTruthy();
    expect(screen.getByText('Are you sure?')).toBeTruthy();

    await userEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(confirmed).toBe(true);
    expect(closed).toBe(true);
  });

  it('does not render when closed', () => {
    const { container } = render(
      <ConfirmDialog
        open={false}
        onClose={() => {}}
        onConfirm={() => {}}
        title="Hidden"
        message="Should not appear"
      />
    );
    expect(container.querySelector('[role="alertdialog"]')).toBeNull();
  });

  it('closes on Escape key', () => {
    let closed = false;
    render(
      <ConfirmDialog
        open={true}
        onClose={() => { closed = true; }}
        onConfirm={() => {}}
        title="Test"
        message="Press escape"
      />
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(closed).toBe(true);
  });
});
