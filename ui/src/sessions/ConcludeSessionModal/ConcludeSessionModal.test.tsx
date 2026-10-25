import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import type { ComponentProps } from "react";
import { ConcludeSessionModal } from "./ConcludeSessionModal";
import { createTestStore, type TestStore } from "@/test/fixtures";
import * as sessionsApi from "@/api/sessions";
import type { ConcludePreview } from "@/types/api";


vi.mock("@/api/sessions", () => ({
  fetchConcludePreview: vi.fn(),
}));

const fetchConcludePreview = vi.mocked(sessionsApi.fetchConcludePreview);

const onClose = vi.fn();
const onConclude = vi.fn();

function makePreview(overrides: Partial<ConcludePreview> = {}): ConcludePreview {
  return {
    is_worktree_session: true,
    branch_has_unmerged_commits: false,
    unmerged_count: 0,
    ...overrides,
  };
}

function renderModal(
  props: Partial<ComponentProps<typeof ConcludeSessionModal>> = {},
  store: TestStore = createTestStore(),
) {
  return render(
    <Provider store={store}>
      <ConcludeSessionModal onClose={onClose} onConclude={onConclude} sessionId="s-1" {...props} />
    </Provider>,
  );
}

const press = (key: string) =>
  fireEvent.keyDown(screen.getByText("Conclude Session").closest("[tabindex]")!, { key });

const settlePreview = () =>
  waitFor(() => expect(fetchConcludePreview).toHaveBeenCalled());

describe("ConcludeSessionModal", () => {
  beforeEach(() => {
    onClose.mockReset();
    onConclude.mockReset();
    fetchConcludePreview.mockReset();
    fetchConcludePreview.mockResolvedValue(makePreview({ is_worktree_session: false }));
  });

  it("renders title and rating options with Neutral selected by default", async () => {
    renderModal();
    expect(screen.getByText("Conclude Session")).toBeInTheDocument();
    for (const label of ["Poor", "Below Average", "Neutral", "Good", "Excellent"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
    expect(screen.getByTestId("rating-3").className).toContain("ratingActive");
    await settlePreview();
  });

  it("selects a rating via click or keyboard number keys", async () => {
    renderModal();
    fireEvent.click(screen.getByTestId("rating-5"));
    expect(screen.getByTestId("rating-5").className).toContain("ratingActive");
    expect(screen.getByTestId("rating-3").className).not.toContain("ratingActive");

    press("4");
    expect(screen.getByTestId("rating-4").className).toContain("ratingActive");
    await settlePreview();
  });

  it("toggles analyze learnings with the A key, but not from the textarea", async () => {
    renderModal();
    const checkbox = screen.getByTestId("analyze-learnings-checkbox") as HTMLInputElement;
    expect(checkbox.checked).toBe(false);

    press("a");
    expect(checkbox.checked).toBe(true);

    press("A");
    expect(checkbox.checked).toBe(false);

    fireEvent.keyDown(screen.getByTestId("feedback-textarea"), { key: "a" });
    expect(checkbox.checked).toBe(false);

    fireEvent.keyDown(screen.getByText("Conclude Session").closest("[tabindex]")!, { key: "a", metaKey: true });
    expect(checkbox.checked).toBe(false);
    await settlePreview();
  });

  it("concludes with defaults via Enter or the Conclude button, but not Enter in the textarea", async () => {
    renderModal();
    fireEvent.keyDown(screen.getByTestId("feedback-textarea"), { key: "Enter" });
    expect(onConclude).not.toHaveBeenCalled();

    press("Enter");
    expect(onConclude).toHaveBeenCalledWith(3, "", true, true, false);

    onConclude.mockReset();
    fireEvent.click(screen.getByText("Conclude"));
    expect(onConclude).toHaveBeenCalledWith(3, "", true, true, false);
    await settlePreview();
  });

  it("propagates selected rating + feedback to onConclude", async () => {
    renderModal();
    press("5");
    fireEvent.change(screen.getByTestId("feedback-textarea"), {
      target: { value: "Great session!" },
    });
    press("Enter");
    expect(onConclude).toHaveBeenCalledWith(5, "Great session!", true, true, false);
    await settlePreview();
  });

  it("restores the store-backed draft after unmount and remount", async () => {
    // The modal unmounts before a conclude can be rejected by the server;
    // the draft must survive in the store so the re-opened modal doesn't
    // reset to rating 3 / empty feedback.
    const store = createTestStore();
    const { unmount } = renderModal({}, store);
    press("5");
    fireEvent.change(screen.getByTestId("feedback-textarea"), {
      target: { value: "keep me" },
    });
    await settlePreview();
    unmount();

    renderModal({}, store);
    expect(screen.getByTestId("rating-5").className).toContain("ratingActive");
    expect((screen.getByTestId("feedback-textarea") as HTMLTextAreaElement).value).toBe("keep me");
    await settlePreview();
  });

  it("calls onClose on Escape", async () => {
    renderModal();
    press("Escape");
    expect(onClose).toHaveBeenCalled();
    await settlePreview();
  });

  it("renders errorDetail when provided", async () => {
    renderModal({ errorDetail: "Something went wrong" });
    expect(screen.getByTestId("conclude-error").textContent).toContain("Something went wrong");
    await settlePreview();
  });

  it("does not render teardown controls for non-worktree sessions", async () => {
    fetchConcludePreview.mockResolvedValue(makePreview({ is_worktree_session: false }));
    renderModal();
    await waitFor(() => expect(fetchConcludePreview).toHaveBeenCalledWith("s-1"));
    expect(screen.queryByTestId("delete-worktree-checkbox")).not.toBeInTheDocument();
    expect(screen.queryByTestId("delete-branch-checkbox")).not.toBeInTheDocument();
  });

  it("renders teardown checkboxes (default on) and sends unchecked flags through onConclude", async () => {
    fetchConcludePreview.mockResolvedValue(makePreview());
    renderModal();
    const wtBox = await screen.findByTestId<HTMLInputElement>("delete-worktree-checkbox");
    const brBox = await screen.findByTestId<HTMLInputElement>("delete-branch-checkbox");
    expect(wtBox.checked).toBe(true);
    expect(brBox.checked).toBe(true);

    fireEvent.click(wtBox);
    fireEvent.click(brBox);
    fireEvent.click(screen.getByText("Conclude"));
    expect(onConclude).toHaveBeenCalledWith(3, "", false, false, false);
  });

  it("renders the unmerged-commits warning when deleting a branch with commits", async () => {
    fetchConcludePreview.mockResolvedValue(
      makePreview({ branch_has_unmerged_commits: true, unmerged_count: 3 }),
    );
    renderModal();
    await screen.findByTestId("unmerged-warning");
    expect(screen.getByTestId("unmerged-warning").textContent).toContain("3");
  });
});
