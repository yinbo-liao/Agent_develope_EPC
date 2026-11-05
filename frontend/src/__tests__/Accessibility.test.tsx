/** Accessibility audit tests for UI primitives. */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/Tabs';
import { Progress } from '../components/ui/Progress';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { ErrorBanner } from '../components/ui/ErrorBanner';

/** Minimal a11y check — verifies ARIA attributes are present. */
function checkAria(element: Element | null, attr: string, value?: string) {
  expect(element).toBeTruthy();
  if (element) {
    const actual = element.getAttribute(attr);
    if (value !== undefined) {
      expect(actual).toBe(value);
    } else {
      expect(actual).not.toBeNull();
    }
  }
}

describe('WCAG 2.1 AA — Tabs', () => {
  it('tablist has role="tablist"', () => {
    const { container } = render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Tab A</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Content A</TabsContent>
      </Tabs>
    );
    checkAria(container.querySelector('[role="tablist"]'), 'role', 'tablist');
  });

  it('tabs have role, aria-selected, aria-controls, tabIndex', () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Tab A</TabsTrigger>
          <TabsTrigger value="b">Tab B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">A</TabsContent>
        <TabsContent value="b">B</TabsContent>
      </Tabs>
    );
    const tabA = document.querySelector('[role="tab"][aria-selected="true"]');
    const tabB = document.querySelector('[role="tab"][aria-selected="false"]');
    expect(tabA).toBeTruthy();
    expect(tabB).toBeTruthy();
    expect(tabA?.getAttribute('aria-controls')).toBeTruthy();
    expect(tabB?.getAttribute('aria-controls')).toBeTruthy();
    // Selected tab has tabIndex=0, unselected tabIndex=-1
    expect(tabA?.getAttribute('tabIndex')).toBe('0');
    expect(tabB?.getAttribute('tabIndex')).toBe('-1');
  });

  it('tabpanel has role and aria-labelledby', () => {
    render(
      <Tabs defaultValue="a">
        <TabsList><TabsTrigger value="a">Tab A</TabsTrigger></TabsList>
        <TabsContent value="a">Content A</TabsContent>
      </Tabs>
    );
    const panel = document.querySelector('[role="tabpanel"]');
    checkAria(panel, 'role', 'tabpanel');
    checkAria(panel, 'aria-labelledby');
  });

  it('inactive tabpanel uses hidden attribute (preserves DOM)', () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Content A</TabsContent>
        <TabsContent value="b">Content B</TabsContent>
      </Tabs>
    );
    const panels = document.querySelectorAll('[role="tabpanel"]');
    expect(panels.length).toBe(2);
    // Only one visible
    expect(panels[0].hasAttribute('hidden')).toBe(false);
    expect(panels[1].hasAttribute('hidden')).toBe(true);
  });
});

describe('WCAG 2.1 AA — Progress', () => {
  it('has progressbar role and aria-valuenow/min/max/text', () => {
    const { container } = render(<Progress value={75} />);
    const bar = container.querySelector('[role="progressbar"]');
    checkAria(bar, 'role', 'progressbar');
    checkAria(bar, 'aria-valuenow', '75');
    checkAria(bar, 'aria-valuemin', '0');
    checkAria(bar, 'aria-valuemax', '100');
    checkAria(bar, 'aria-valuetext', '75% complete');
  });

  it('clamps value to 0-100', () => {
    const { container: c1 } = render(<Progress value={150} />);
    expect(c1.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('100');

    const { container: c2 } = render(<Progress value={-10} />);
    expect(c2.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('0');
  });

  it('uses custom label when provided', () => {
    const { container } = render(<Progress value={60} label="60 of 100 drawings" />);
    checkAria(container.querySelector('[role="progressbar"]'), 'aria-valuetext', '60 of 100 drawings');
  });
});

describe('WCAG 2.1 AA — Button', () => {
  it('has type="button" by default (not submit)', () => {
    render(<Button>Save</Button>);
    const btn = document.querySelector('button');
    expect(btn?.getAttribute('type')).toBe('button');
  });

  it('has aria-disabled when disabled', () => {
    render(<Button disabled>Save</Button>);
    const btn = document.querySelector('button');
    expect(btn?.getAttribute('aria-disabled')).toBe('true');
  });
});

describe('WCAG 2.1 AA — Badge', () => {
  it('renders as a span (semantic non-interactive)', () => {
    const { container } = render(<Badge variant="success">Done</Badge>);
    const element = container.querySelector('span');
    expect(element?.tagName).toBe('SPAN');
  });
});

describe('WCAG 2.1 AA — ErrorBanner', () => {
  it('displays accessible error with icon', () => {
    render(<ErrorBanner title="Error" message="Test error message" />);
    expect(document.querySelector('svg')).toBeTruthy();
    expect(document.body.textContent).toContain('Error');
    expect(document.body.textContent).toContain('Test error message');
  });
});
