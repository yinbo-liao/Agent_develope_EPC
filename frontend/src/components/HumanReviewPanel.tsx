import { useState } from "react";

import type { WorkflowReviewData } from "../types/workflow";

export function HumanReviewPanel({
  details,
  onDecision,
}: {
  details?: WorkflowReviewData;
  onDecision: (decision: "approved" | "rejected", comment: string) => Promise<void>;
}) {
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState<"approved" | "rejected" | null>(null);

  const decide = async (decision: "approved" | "rejected") => {
    setPending(decision);
    try {
      await onDecision(decision, comment);
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
      <h3 className="text-lg font-semibold text-amber-900">Human Review Required</h3>
      <p className="mt-2 text-sm text-amber-800">
        This workflow paused for review. The decision is recorded against your account.
      </p>
      {details?.deadline ? (
        <p className="mt-2 text-sm text-amber-800">
          Deadline: {new Date(details.deadline).toLocaleString()}
        </p>
      ) : null}
      <div className="mt-4 space-y-3">
        <label className="text-sm font-medium text-amber-900" htmlFor="review-comment">
          Review note
        </label>
        <textarea
          id="review-comment"
          className="min-h-24 w-full rounded-xl border border-amber-200 bg-white px-3 py-2 text-sm"
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="Record why you approve or reject this run"
        />
        {details?.factors?.length ? (
          <div className="rounded-xl bg-white p-3 text-sm text-amber-900">
            <p className="font-medium">Risk factors</p>
            <ul className="mt-2 space-y-1">
              {details.factors.map((factor) => (
                <li key={factor}>{factor}</li>
              ))}
            </ul>
          </div>
        ) : null}
        <div className="flex gap-3">
          <button
            className="rounded-xl bg-accent-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            disabled={pending !== null}
            onClick={() => void decide("approved")}
          >
            {pending === "approved" ? "Approving..." : "Approve"}
          </button>
          <button
            className="rounded-xl border border-amber-300 px-4 py-2 text-sm font-medium text-amber-900 disabled:opacity-60"
            disabled={pending !== null}
            onClick={() => void decide("rejected")}
          >
            {pending === "rejected" ? "Rejecting..." : "Reject"}
          </button>
        </div>
      </div>
    </div>
  );
}