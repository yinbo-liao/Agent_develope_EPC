import { useState, createContext, useContext, useCallback, useId, type ReactNode, type KeyboardEvent } from 'react';
import { clsx } from 'clsx';

interface TabsContextValue {
  value: string;
  onChange: (v: string) => void;
  tabsId: string;
}

const TabsContext = createContext<TabsContextValue>({ value: '', onChange: () => {}, tabsId: '' });

export function Tabs({ defaultValue, children, className }: { defaultValue: string; children: ReactNode; className?: string }) {
  const [value, setValue] = useState(defaultValue);
  const tabsId = useId();
  return (
    <TabsContext.Provider value={{ value, onChange: setValue, tabsId }}>
      <div className={clsx('space-y-4', className)}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="tablist" className={clsx('flex flex-wrap gap-1 bg-slate-900/60 p-1 rounded-lg border border-slate-700', className)}>
      {children}
    </div>
  );
}

export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  const active = ctx.value === value;
  const panelId = `${ctx.tabsId}-panel-${value}`;
  const tabId = `${ctx.tabsId}-tab-${value}`;

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLButtonElement>) => {
    const tabs = document.querySelectorAll<HTMLElement>(`[role="tab"][data-tabs-id="${ctx.tabsId}"]`);
    const current = Array.from(tabs).indexOf(e.currentTarget as HTMLElement);
    let next: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (current + 1) % tabs.length;
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (current - 1 + tabs.length) % tabs.length;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = tabs.length - 1;
    if (next !== null) {
      e.preventDefault();
      (tabs[next] as HTMLElement).focus();
    }
  }, [ctx.tabsId]);

  return (
    <button
      role="tab"
      id={tabId}
      data-tabs-id={ctx.tabsId}
      aria-selected={active}
      aria-controls={panelId}
      tabIndex={active ? 0 : -1}
      onClick={() => ctx.onChange(value)}
      onKeyDown={handleKeyDown}
      className={clsx(
        'px-4 py-2 text-sm font-medium rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary',
        active ? 'bg-primary text-white shadow' : 'text-slate-400 hover:text-white hover:bg-slate-700/50',
      )}>
      {children}
    </button>
  );
}

export function TabsContent({ value, children }: { value: string; children: ReactNode }) {
  const ctx = useContext(TabsContext);
  const active = ctx.value === value;
  const panelId = `${ctx.tabsId}-panel-${value}`;
  const tabId = `${ctx.tabsId}-tab-${value}`;

  return (
    <div
      role="tabpanel"
      id={panelId}
      aria-labelledby={tabId}
      hidden={!active}
      tabIndex={0}
    >
      {children}
    </div>
  );
}
