import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, fireEvent, screen, waitFor } from "@testing-library/react";
import { HarnessExplorer } from "./HarnessExplorer";
import * as filesApi from "@/api/files";
import * as harnessContext from "./useHarness";

vi.mock("@/api/files");

function mockHarness(overrides: Partial<ReturnType<typeof harnessContext.useHarness>> = {}) {
  vi.spyOn(harnessContext, "useHarness").mockReturnValue({
    loading: false,
    error: null,
    tree: [{ name: "main.py", path: "main.py", is_dir: false, git_status: null, children: null }],
    selectedPath: null,
    fileContent: null,
    fileLoading: false,
    fileError: null,
    expandedPaths: [],
    selectPath: vi.fn(),
    setExpandedPaths: vi.fn(),
    refresh: vi.fn(),
    ...overrides,
  });
}

describe("HarnessExplorer export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHarness();
  });

  it("triggers a config download when the export button is clicked", async () => {
    const download = vi
      .spyOn(filesApi, "downloadHarnessConfig")
      .mockResolvedValue(undefined);

    render(<HarnessExplorer />);
    fireEvent.click(screen.getByLabelText("Export config"));

    await waitFor(() => expect(download).toHaveBeenCalledTimes(1));
  });

  it("shows an error when the export fails", async () => {
    vi.spyOn(filesApi, "downloadHarnessConfig").mockRejectedValue(
      new Error("nope"),
    );

    render(<HarnessExplorer />);
    fireEvent.click(screen.getByLabelText("Export config"));

    expect(await screen.findByText("nope")).toBeInTheDocument();
  });
});
