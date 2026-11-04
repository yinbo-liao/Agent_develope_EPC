import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { authFetch } from "../lib/auth";
import { runtimeConfig } from "../lib/runtime";
import type { WorkflowEvent, WorkflowState } from "../types/workflow";

const STREAM_ERROR = "The live event stream could not be opened. Refresh to retry.";

const emptyState = (taskId: string): WorkflowState => ({
  taskId,
  status: "idle",
  currentStep: "not-started",
  finalResponse: null,
  error: null,
  isHumanReviewNeeded: false,
  reviewData: undefined,
  totalTokens: 0,
  totalCost: 0,
  steps: [],
  transport: "connecting",
  connected: false,
});

function parseEvent(raw: string): WorkflowEvent | null {
  try {
    return JSON.parse(raw) as WorkflowEvent;
  } catch {
    return null;
  }
}

export function useWorkflowEvents(taskId: string | null, token: string) {
  const [state, setState] = useState<WorkflowState>(emptyState(taskId ?? ""));
  const socketRef = useRef<WebSocket | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const closeStreams = useCallback(() => {
    socketRef.current?.close();
    sourceRef.current?.close();
    socketRef.current = null;
    sourceRef.current = null;
  }, []);

  const applyEvent = useCallback((event: WorkflowEvent) => {
    setState((current) => {
      const stepName = event.stepName ?? event.currentStep;
      const nextSteps =
        stepName === undefined
          ? current.steps
          : current.steps.some((step) => step.stepName === stepName && step.status === event.stepStatus)
            ? current.steps
            : [
                ...current.steps,
                {
                  stepName,
                  status: event.stepStatus ?? event.status ?? "updated",
                  timestamp: event.timestamp,
                },
              ];
      return {
        ...current,
        taskId: event.taskId || current.taskId,
        status:
          event.type === "error"
            ? "error"
            : event.isHumanReviewNeeded
              ? "paused"
              : ((event.status as WorkflowState["status"]) ?? current.status),
        currentStep: event.currentStep ?? event.stepName ?? current.currentStep,
        finalResponse: event.finalResponse ?? current.finalResponse,
        error: event.error ?? current.error,
        isHumanReviewNeeded: event.isHumanReviewNeeded ?? current.isHumanReviewNeeded,
        reviewData: event.reviewData ?? current.reviewData,
        totalTokens: event.totalTokens ?? current.totalTokens,
        totalCost: event.totalCost ?? current.totalCost,
        steps: nextSteps,
        connected: true,
      };
    });
  }, []);

  const refresh = useCallback(async () => {
    if (!taskId) {
      return;
    }
    const response = await authFetch(`${runtimeConfig.apiBase}/api/v1/events/state/${taskId}`);
    if (!response.ok) {
      throw new Error("Failed to fetch workflow state");
    }
    applyEvent((await response.json()) as WorkflowEvent);
  }, [applyEvent, taskId]);

  const sendResume = useCallback(
    async (decision: "approved" | "rejected", comment: string) => {
      if (!taskId) {
        return;
      }
      const response = await authFetch(`${runtimeConfig.apiBase}/api/v1/human-review/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId, decision, comment }),
      });
      if (!response.ok) {
        const detail = response.status === 403 ? "You are not allowed to decide this run."
          : response.status === 409 ? "This run is no longer awaiting review."
            : "The decision could not be recorded.";
        setState((current) => ({ ...current, error: detail }));
        return;
      }
      await refresh();
    },
    [refresh, taskId],
  );

  useEffect(() => {
    if (!taskId) {
      closeStreams();
      return;
    }

    let disposed = false;
    setState(emptyState(taskId));

    const connectSse = (ticket: string) => {
      if (disposed) {
        return;
      }
      const source = new EventSource(
        `${runtimeConfig.apiBase}/api/v1/events/sse/${taskId}?ticket=${encodeURIComponent(ticket)}`,
      );
      sourceRef.current = source;
      source.onopen = () => {
        setState((current) => ({ ...current, transport: "sse", connected: true }));
      };
      source.onmessage = (message) => {
        const event = parseEvent(message.data);
        if (event) {
          applyEvent(event);
        }
      };
      source.onerror = () => {
        source.close();
        if (!disposed) {
          setState((current) => ({ ...current, connected: false, error: STREAM_ERROR }));
        }
      };
    };

    const connectWebSocket = (ticket: string) => {
      if (disposed) {
        return;
      }
      const socket = new WebSocket(
        `${runtimeConfig.wsBase}/api/v1/events/ws/${taskId}?ticket=${encodeURIComponent(ticket)}`,
      );
      socketRef.current = socket;
      socket.onopen = () => {
        setState((current) => ({ ...current, transport: "websocket", connected: true }));
      };
      socket.onmessage = (message) => {
        const event = parseEvent(String(message.data));
        if (event) {
          applyEvent(event);
        }
      };
      socket.onclose = () => {
        if (!disposed) {
          connectSse(ticket);
        }
      };
    };

    const start = async () => {
      try {
        const response = await authFetch(
          `${runtimeConfig.apiBase}/api/v1/events/ticket/${taskId}`,
          { method: "POST" },
        );
        if (!response.ok) {
          throw new Error(STREAM_ERROR);
        }
        const { ticket } = (await response.json()) as { ticket: string };
        if (!disposed) {
          connectWebSocket(ticket);
        }
      } catch {
        if (!disposed) {
          setState((current) => ({ ...current, connected: false, error: STREAM_ERROR }));
        }
      }
    };

    void refresh().catch(() => undefined);
    void start();

    return () => {
      disposed = true;
      closeStreams();
    };
  }, [applyEvent, closeStreams, refresh, taskId, token]);

  return useMemo(
    () => ({ state, sendResume, refresh }),
    [refresh, sendResume, state],
  );
}