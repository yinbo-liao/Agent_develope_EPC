import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { HumanReviewPanel } from "./HumanReviewPanel";

describe("HumanReviewPanel", () => {
  it("submits the comment with the decision", async () => {
    const user = userEvent.setup();
    const onDecision = vi.fn().mockResolvedValue(undefined);

    render(
      <HumanReviewPanel
        details={{ factors: ["Destructive operation"], deadline: null }}
        onDecision={onDecision}
      />,
    );

    await user.type(screen.getByLabelText(/review note/i), "checked the plan");
    await user.click(screen.getByRole("button", { name: /^approve$/i }));

    await waitFor(() => {
      expect(onDecision).toHaveBeenCalledWith("approved", "checked the plan");
    });
  });

  it("shows risk factors and deadline", () => {
    render(
      <HumanReviewPanel
        details={{
          factors: ["Destructive operation"],
          deadline: "2030-01-01T00:00:00Z",
        }}
        onDecision={vi.fn()}
      />,
    );

    expect(screen.getByText("Destructive operation")).toBeInTheDocument();
    expect(screen.getByText(/deadline/i)).toBeInTheDocument();
  });
});