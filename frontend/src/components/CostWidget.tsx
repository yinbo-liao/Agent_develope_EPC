import { useEffect, useState } from "react";

import { authFetch } from "../lib/auth";
import { runtimeConfig } from "../lib/runtime";

type CostStatus = {
  current_cost_usd: number;
  daily_limit_usd: number;
  usage_percent: number;
  tokens_used: number;
  model_breakdown: Array<{ model: string; tokens: number }>;
  alerts: Array<{ threshold: number; triggered_at: string }>;
  budget_tier: string;
};

export function CostWidget() {
  const [data, setData] = useState<CostStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await authFetch(`${runtimeConfig.apiBase}/api/v1/cost/status`);
        if (!response.ok) {
          throw new Error("Failed to load cost status");
        }
        const payload = (await response.json()) as CostStatus;
        if (!cancelled) {
          setData(payload);
          setError(null);
        }
      } catch (costError) {
        if (!cancelled) {
          setError(costError instanceof Error ? costError.message : "Unknown error");
        }
      }
    };

    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  if (error) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700" role="alert">
        {error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="rounded-2xl border border-neutral-200 bg-white p-5 text-sm text-neutral-500 shadow-soft">
        Loading cost status...
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-soft">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-neutral-900">Cost Governance</h3>
        <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-medium text-neutral-700">
          {data.budget_tier}
        </span>
      </div>
      <div className="mt-4 space-y-4">
        <div>
          <div className="flex items-center justify-between text-sm text-neutral-600">
            <span>Daily budget</span>
            <span>
              ${data.current_cost_usd.toFixed(4)} / ${data.daily_limit_usd.toFixed(2)}
            </span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-neutral-100">
            <div
              className="h-2 rounded-full bg-primary-600"
              style={{ width: `${Math.min(100, data.usage_percent)}%` }}
            />
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-neutral-50 p-4">
            <p className="text-sm text-neutral-500">Usage</p>
            <p className="mt-2 font-mono text-xl text-neutral-900">{data.usage_percent}%</p>
          </div>
          <div className="rounded-xl bg-neutral-50 p-4">
            <p className="text-sm text-neutral-500">Tokens today</p>
            <p className="mt-2 font-mono text-xl text-neutral-900">
              {data.tokens_used.toLocaleString()}
            </p>
          </div>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-neutral-900">Model usage</h4>
          <div className="mt-2 space-y-2 text-sm text-neutral-600">
            {data.model_breakdown.length === 0 ? (
              <p>No recorded model activity yet.</p>
            ) : (
              data.model_breakdown.map((entry) => (
                <div key={entry.model} className="flex items-center justify-between">
                  <span>{entry.model}</span>
                  <span className="font-mono">{entry.tokens.toLocaleString()} tokens</span>
                </div>
              ))
            )}
          </div>
        </div>
        {data.alerts.length ? (
          <div>
            <h4 className="text-sm font-semibold text-neutral-900">Alerts</h4>
            <div className="mt-2 space-y-2 text-sm text-amber-700">
              {data.alerts.map((alert) => (
                <div key={`${alert.threshold}-${alert.triggered_at}`}>
                  {alert.threshold}% threshold reached at{" "}
                  {new Date(alert.triggered_at).toLocaleTimeString()}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}