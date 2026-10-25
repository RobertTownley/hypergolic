import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { Provider } from "react-redux";
import { MergeReviewTakeover } from "./MergeReviewTakeover";
import { type PendingApproval } from "@/store/messagesSlice";
import { createTestStore } from "@/test/fixtures";
import type { GitReviewResponse } from "@/types/api";

const sendApprovalResponse = vi.fn();
vi.mock("@/api/WebSocketProvider", () => ({
  useWebSocket: () => ({ sendApprovalResponse }),
}));

const REVIEW: GitReviewResponse = {
  session_id: "s1",
  branch: "feat",
  base_branch: "main",
  merge_base: "abc",
  ahead: 2,
  behind: 0,
  commits: [
    { hash: "h1", short_hash: "h1", author: "a", date: "d", message: "first", refs: "" },
  ],
  files: [
    {
      path: "a.py",
      old_path: null,
      status: "M",
      additions: 1,
      deletions: 1,
      patch: "@@ -1,2 +1,2 @@\n context\n-old\n+new\n",
    },
    {
      path: "src/nested/b.py",
      old_path: null,
      status: "A",
      additions: 3,
      deletions: 0,
      patch: "@@ -0,0 +1,3 @@\n+x\n+y\n+z\n",
    },
  ],
};

const fetchGitReview = vi.fn(() => Promise.resolve(REVIEW));
vi.mock("@/api/git", () => ({
  fetchGitReview: (...args: unknown[]) => fetchGitReview(...(args as [])),
}));

function makeApproval(): PendingApproval {
  return {
    toolUseId: "tu1",
    toolName: "Merge",
    toolId: "land",
    toolInput: { repo: "app", commit_message: "Do the thing\n\nBecause of reasons." },
    sessionId: "s1",
  };
}

function renderTakeover(approval: PendingApproval | null = makeApproval()) {
  const store = createTestStore();
  return {
    store,
    ...render(
      <Provider store={store}>
        <MergeReviewTakeover sessionId="s1" approval={approval} />
      </Provider>
    ),
  };
}

beforeEach(() => {
  sendApprovalResponse.mockClear();
});

describe("MergeReviewTakeover", () => {
  it("renders branches, files, and diff after loading", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    expect(screen.getByText("main")).toBeTruthy();
    // Default selection follows the rail's visual (tree) order: dirs first
    expect(screen.getByText("x")).toBeTruthy();
    fireEvent.click(screen.getByText("a.py"));
    expect(screen.getByText("new")).toBeTruthy();
    expect(screen.getByText("Approve merge")).toBeTruthy();
  });

  it("shows the agent's description as markdown and collapses it", async () => {
    const approval = makeApproval();
    approval.toolInput.description = "## Why\n\nFixes **the bug**.";
    renderTakeover(approval);
    await waitFor(() => expect(screen.getByText("the bug")).toBeTruthy());
    expect(screen.getByRole("heading", { name: "Why" })).toBeTruthy();
    fireEvent.click(screen.getByText("Hide description"));
    expect(screen.queryByText("the bug")).toBeNull();
    expect(screen.getByText("Why")).toBeTruthy();
  });

  it("reviews the land target branch named by the approval", async () => {
    const approval = makeApproval();
    approval.toolInput.arguments = {
      sha: "a".repeat(40), base_sha: "b".repeat(40), branch: "ABC-1204",
    };
    renderTakeover(approval);
    await waitFor(() => expect(screen.getByText("Merge into ABC-1204")).toBeTruthy());
    expect(fetchGitReview).toHaveBeenCalledWith(
      { sessionId: "s1", repoScope: "app" },
      { head: "a".repeat(40), base: "b".repeat(40), branch: "ABC-1204", view: "merge" },
    );
  });

  it("explains a clean merge candidate and toggles to the full range", async () => {
    const clean: GitReviewResponse = {
      ...REVIEW, files: [],
      merge: { parents: ["p1", "p2"], merged_from: "main", merged_count: 26, conflict_paths: [], view: "merge" },
    };
    fetchGitReview.mockResolvedValueOnce(clean);
    fetchGitReview.mockResolvedValueOnce({ ...REVIEW, merge: { ...clean.merge!, view: "range" } });
    const approval = makeApproval();
    approval.toolInput.arguments = { sha: "a".repeat(40), base_sha: "b".repeat(40), branch: "pr" };
    renderTakeover(approval);
    await waitFor(() =>
      expect(screen.getByText("Clean merge of 26 commits from main; no conflict resolutions")).toBeTruthy(),
    );
    expect(screen.getByText("No conflict resolutions to review")).toBeTruthy();
    fireEvent.click(screen.getByText("Show full range diff"));
    await waitFor(() => expect(screen.getByText("a.py")).toBeTruthy());
    expect(fetchGitReview).toHaveBeenLastCalledWith(
      { sessionId: "s1", repoScope: "app" },
      { head: "a".repeat(40), base: "b".repeat(40), branch: "pr", view: "range" },
    );
    expect(screen.getByText("Show conflict resolutions only")).toBeTruthy();
  });

  it("renders changed files as a directory tree", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    expect(screen.getByText("src")).toBeTruthy();
    expect(screen.getByText("nested")).toBeTruthy();
    expect(screen.getByText("b.py")).toBeTruthy();
    fireEvent.click(screen.getByText("src"));
    expect(screen.queryByText("b.py")).toBeNull();
  });

  it("shows the merge commit message prominently with expandable body", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    expect(screen.getByText("Do the thing")).toBeTruthy();
    expect(screen.queryByText("Because of reasons.")).toBeNull();
    fireEvent.click(screen.getByText("Show full message"));
    expect(screen.getByText("Because of reasons.")).toBeTruthy();
    fireEvent.click(screen.getByText("Hide full message"));
    expect(screen.queryByText("Because of reasons.")).toBeNull();
  });

  it("hides the action bar in ambient mode", async () => {
    renderTakeover(null);
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    expect(screen.queryByText("Approve merge")).toBeNull();
    expect(screen.getByText("Reviewing vs base")).toBeTruthy();
  });

  it("approve sends an approval response", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("Approve merge")).toBeTruthy());
    fireEvent.click(screen.getByText("Approve merge"));
    await waitFor(() =>
      expect(sendApprovalResponse).toHaveBeenCalledWith("s1", "tu1", true, undefined, undefined)
    );
  });

  it("queues an inline comment and sends it on request changes", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("a.py")).toBeTruthy());
    fireEvent.click(screen.getByText("a.py"));
    fireEvent.click(screen.getByText("new"));
    const textarea = await screen.findByPlaceholderText("Comment for the agent…");
    fireEvent.change(textarea, { target: { value: "why?" } });
    fireEvent.click(screen.getByText("Add comment"));
    expect(screen.getByText("1 inline comment queued")).toBeTruthy();

    fireEvent.click(screen.getByText("Request changes"));
    await waitFor(() => expect(sendApprovalResponse).toHaveBeenCalled());
    const [sid, tuid, approved, reason, annotations] = sendApprovalResponse.mock.calls[0];
    expect([sid, tuid, approved]).toEqual(["s1", "tu1", false]);
    expect(reason).toBe("See inline review comments.");
    expect(annotations).toHaveLength(1);
    expect(annotations[0].highlighted_text).toBe("a.py:2");
    expect(annotations[0].comment).toBe("why?");
  });

  it("close dismisses the pending approval", async () => {
    const { store } = renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    fireEvent.click(screen.getByText("Back to session"));
    expect(store.getState().review.bySession["s1"].dismissedToolUseIds).toEqual({ tu1: true });
  });

  it("marking viewed with 'v' advances to the next file", async () => {
    const { store } = renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    // Default selection is the first file in tree order (src/nested/b.py)
    fireEvent.keyDown(window, { key: "v" });
    const state = store.getState().review.bySession["s1"];
    expect(state.viewed["src/nested/b.py"]).toBe(true);
    expect(state.selectedPath).toBe("a.py");
  });

  it("arrow keys scroll the diff area", async () => {
    renderTakeover();
    await waitFor(() => expect(screen.getByText("feat")).toBeTruthy());
    const diffArea = document.querySelector('[class*="diffArea"]') as HTMLElement;
    const scrollBy = vi.fn();
    diffArea.scrollBy = scrollBy;
    fireEvent.keyDown(window, { key: "ArrowDown" });
    expect(scrollBy).toHaveBeenCalledWith({ top: 120 });
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(scrollBy).toHaveBeenCalledWith({ top: -120 });
  });
});
