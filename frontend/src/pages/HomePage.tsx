import { useCallback, useEffect, useState } from "react";

import { CostWidget } from "../components/CostWidget";
import { WorkflowDashboard } from "../components/WorkflowDashboard";
import { authFetch, type Session } from "../lib/auth";
import { runtimeConfig } from "../lib/runtime";
import type { WorkflowSummary } from "../types/workflow";

export function HomePage({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const [query, setQuery] = useState("Review the deployment change plan for security impact.");
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [recentRuns, setRecentRuns] = useState<WorkflowSummary[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRuns = useCallback(async () => {
    const response = await authFetch(`${runtimeConfig.apiBase}/api/v1/workflows?limit=10`);
    if (!response.ok) {
      throw new Error("Failed to load workflows");
    }
    const payload = (await response.json()) as { items: WorkflowSummary[] };
    setRecentRuns(payload.items);
  }, []);

  useEffect(() => {
    void loadRuns().catch(() => undefined);
  }, [loadRuns]);

  const createWorkflow = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await authFetch(`${runtimeConfig.apiBase}/api/v1/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          input_query: query,
          token_budget: 10000,
          cost_budget_usd: 5,
        }),
      });
      if (!response.ok) {
        throw new Error(
          response.status === 401 ? "Your session expired. Please sign in again." : "Failed to create workflow",
        );
      }
      const workflow = (await response.json()) as WorkflowSummary;
      setActiveTaskId(workflow.id);
      setRecentRuns((current) => [workflow, ...current].slice(0, 10));
    } catch (submissionError) {
      setError(submissionError instanceof Error ? submissionError.message : "Unknown error");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="min-h-screen bg-neutral-50 text-neutral-900">
      <section className="mx-auto flex max-w-7xl flex-col gap-10 px-6 py-16">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-4xl space-y-5">
            <span className="inline-flex rounded-full border border-primary-100 bg-primary-50 px-3 py-1 text-sm font-medium text-primary-700">
              Wave 3 Monitoring
            </span>
            <h1 className="text-4xl font-semibold tracking-tight text-neutral-900">
              AI Workflow Platform
            </h1>
            <p className="text-lg leading-8 text-neutral-600">
              Create a workflow run, attach to its live event stream, and inspect step
              progression or human review state from the dashboard below.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl border border-neutral-200 bg-white px-4 py-3 text-sm shadow-soft">
            <div>
              <p className="font-medium text-neutral-900">{session.userId}</p>
              <p className="text-xs uppercase tracking-wide text-neutral-500">{session.role}</p>
            </div>
            <button
              className="rounded-xl border border-neutral-200 px-3 py-1.5 text-sm font-medium text-neutral-700"
              onClick={onLogout}
            >
              Sign out
            </button>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[0.9fr,1.1fr]">
          <div className="space-y-6">
            <div className="rounded-2xl border border-neutral-200 bg-white p-6 shadow-soft">
              <h2 className="text-lg font-semibold text-neutral-900">Launch Workflow</h2>
              <div className="mt-4 space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-neutral-700" htmlFor="workflow-query">
                    Workflow request
                  </label>
                  <textarea
                    id="workflow-query"
                    className="min-h-40 w-full rounded-2xl border border-neutral-200 px-4 py-3 text-sm"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Describe the workflow you want to run"
                  />
                </div>
                <button
                  className="rounded-2xl bg-primary-600 px-5 py-3 text-sm font-medium text-white disabled:opacity-60"
                  disabled={isSubmitting || query.trim().length < 3}
                  onClick={() => void createWorkflow()}
                >
                  {isSubmitting ? "Creating..." : "Create and monitor workflow"}
                </button>
                {error ? (
                  <p className="text-sm text-red-600" role="alert">
                    {error}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="rounded-2xl border border-neutral-200 bg-white p-6 shadow-soft">
              <h2 className="text-lg font-semibold text-neutral-900">Recent Runs</h2>
              <div className="mt-4 space-y-3">
                {recentRuns.length === 0 ? (
                  <p className="text-sm text-neutral-500">No runs yet.</p>
                ) : (
                  recentRuns.map((run) => (
                    <button
                      key={run.id}
                      className="flex w-full items-center justify-between rounded-xl border border-neutral-200 px-4 py-3 text-left"
                      onClick={() => setActiveTaskId(run.id)}
                    >
                      <span className="font-mono text-xs text-neutral-600">{run.id}</span>
                      <span className="text-sm text-neutral-900">{run.current_status}</span>
                    </button>
                  ))
                )}
              </div>
            </div>

            <CostWidget />
          </div>

          <div>
            {activeTaskId ? (
              <WorkflowDashboard taskId={activeTaskId} token={session.token} />
            ) : (
              <div className="rounded-2xl border border-dashed border-neutral-300 bg-white p-8 text-sm text-neutral-500 shadow-soft">
                Create a workflow to open the realtime dashboard.
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}