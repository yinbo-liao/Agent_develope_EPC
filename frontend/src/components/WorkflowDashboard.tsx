import { ErrorBoundary } from "./ErrorBoundary";
import { CostDisplay } from "./CostDisplay";
import { HumanReviewPanel } from "./HumanReviewPanel";
import { ReActThoughtViewer } from "./ReActThoughtViewer";
import { StepTimeline } from "./StepTimeline";
import { TransportIndicator } from "./TransportIndicator";
import { useWorkflowEvents } from "../hooks/useWorkflowEvents";

export function WorkflowDashboard({ taskId, token }: { taskId: string; token: string }) {
  const { state, sendResume, refresh } = useWorkflowEvents(taskId, token);

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-neutral-200 bg-white p-5 shadow-soft">
          <div>
            <p className="text-sm text-neutral-500">Watching task</p>
            <h2 className="font-mono text-lg text-neutral-900">{taskId}</h2>
          </div>
          <div className="flex items-center gap-3">
            <TransportIndicator transport={state.transport} />
            <button
              className="rounded-xl border border-neutral-200 px-4 py-2 text-sm font-medium text-neutral-700"
              onClick={() => void refresh()}
            >
              Refresh snapshot
            </button>
          </div>
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
          <div className="space-y-6">
            <StepTimeline steps={state.steps} currentStep={state.currentStep} />
            <ReActThoughtViewer
              summary={state.finalResponse}
              factors={state.reviewData?.factors ?? []}
            />
          </div>

          <div className="space-y-6">
            <div className="rounded-2xl border border-neutral-200 bg-white p-5 shadow-soft">
              <h3 className="text-lg font-semibold text-neutral-900">Current Status</h3>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">Status</span>
                  <span className="font-medium text-neutral-900">{state.status}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">Current step</span>
                  <span className="font-medium text-neutral-900">{state.currentStep}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">Connected</span>
                  <span className="font-medium text-neutral-900">
                    {state.connected ? "Yes" : "No"}
                  </span>
                </div>
              </div>
            </div>

            <CostDisplay totalTokens={state.totalTokens} totalCost={state.totalCost} />

            {state.isHumanReviewNeeded ? (
              <HumanReviewPanel
                details={state.reviewData}
                onDecision={(decision, comment) => sendResume(decision, comment)}
              />
            ) : null}

            {state.error ? (
              <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700" role="alert">
                {state.error}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}