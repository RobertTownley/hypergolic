import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionConclusion } from "./SessionConclusion";

// Mock icons
vi.mock("lucide-react", () => ({
  StarIcon: ({ fill }: { fill?: string }) => (
    <span data-testid={fill ? "star-filled" : "star-outlined"} />
  ),
  ClockIcon: () => <span data-testid="clock-icon" />,
  MessageSquareIcon: () => <span data-testid="message-icon" />,
}));

describe("SessionConclusion", () => {
  it("should render the component", () => {
    render(
      <SessionConclusion
        conclusionRating={4}
        conclusionFeedback={null}
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    expect(screen.getByTestId("session-conclusion")).toBeInTheDocument();
    expect(screen.getByText("Session Concluded")).toBeInTheDocument();
  });

  it("should display rating stars", () => {
    render(
      <SessionConclusion
        conclusionRating={4}
        conclusionFeedback={null}
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    const stars = screen.getByTestId("rating-stars");
    const filled = stars.querySelectorAll("[data-testid='star-filled']");
    const outlined = stars.querySelectorAll("[data-testid='star-outlined']");
    expect(filled).toHaveLength(4);
    expect(outlined).toHaveLength(1);
  });

  it("should display feedback when present", () => {
    render(
      <SessionConclusion
        conclusionRating={4}
        conclusionFeedback="This was helpful"
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    expect(screen.getByTestId("conclusion-feedback")).toHaveTextContent("This was helpful");
  });

  it("should not display feedback section when feedback is null", () => {
    render(
      <SessionConclusion
        conclusionRating={4}
        conclusionFeedback={null}
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    expect(screen.queryByTestId("conclusion-feedback")).not.toBeInTheDocument();
  });

  it("should display concluded timestamp", () => {
    render(
      <SessionConclusion
        conclusionRating={3}
        conclusionFeedback={null}
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    const meta = screen.getByTestId("clock-icon").parentElement;
    expect(meta).toBeTruthy();
    expect(meta!.textContent).toBeTruthy();
  });

  it("should handle null rating", () => {
    render(
      <SessionConclusion
        conclusionRating={null}
        conclusionFeedback={null}
        concludedAt="2025-01-15T10:30:00Z"
      />,
    );
    expect(screen.queryByTestId("rating-stars")).not.toBeInTheDocument();
  });

  it("should handle null concluded_at", () => {
    render(
      <SessionConclusion
        conclusionRating={3}
        conclusionFeedback={null}
        concludedAt={null}
      />,
    );
    expect(screen.queryByTestId("clock-icon")).not.toBeInTheDocument();
  });
});
