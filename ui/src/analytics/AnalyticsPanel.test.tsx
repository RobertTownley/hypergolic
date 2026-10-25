import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AnalyticsPanel } from "./AnalyticsPanel";

vi.mock("./UsageView", () => ({ UsageView: () => <div data-testid="usage" /> }));
vi.mock("./performance/PerformanceView", () => ({
  PerformanceView: () => <div data-testid="performance" />,
}));

describe("AnalyticsPanel", () => {
  it("opens on usage and switches to performance", () => {
    render(<AnalyticsPanel />);
    expect(screen.getByTestId("usage")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Performance & Observability/ }));
    expect(screen.getByTestId("performance")).toBeInTheDocument();
    expect(screen.queryByTestId("usage")).not.toBeInTheDocument();
  });
});
