import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { Provider } from "react-redux";
import { ProjectsPanel } from "./index";
import type { Project } from "@/types/api";
import { createTestStore, makeProject } from "@/test/fixtures";

function makeStore(projects: Project[]) {
  const entities: Record<string, Project> = {};
  const ids: string[] = [];
  for (const p of projects) {
    entities[p.id] = p;
    ids.push(p.id);
  }
  return createTestStore({
    projects: {
      entities,
      ids,
      initialized: true,
      loading: false,
      error: null,
      branchesByProjectId: {},
      rolesByProjectId: {},
    },
  });
}

function renderWithProjects(projects: Project[]) {
  const store = makeStore(projects);
  return render(
    <Provider store={store}>
      <ProjectsPanel />
    </Provider>,
  );
}

describe("ProjectsPanel", () => {
  it("renders the tool icon for the harness project row", () => {
    const { container } = renderWithProjects([
      makeProject({ id: "harness", name: "My Harness", path: "/Users/x/.hypergolic" }),
      makeProject({ id: "regular", name: "Regular", path: "/Users/x/code" }),
    ]);
    const rows = container.querySelectorAll("[class*='projectRow']");
    expect(rows.length).toBe(2);

    const harnessRow = Array.from(rows).find((r) =>
      r.textContent?.includes("My Harness"),
    );
    const regularRow = Array.from(rows).find((r) =>
      r.textContent?.includes("Regular"),
    );
    expect(harnessRow).toBeDefined();
    expect(regularRow).toBeDefined();

    expect(harnessRow!.querySelector(".lucide-wrench")).not.toBeNull();
    expect(regularRow!.querySelector(".lucide-wrench")).toBeNull();
  });

  it("does not render the tool icon when no harness project is present", () => {
    const { container } = renderWithProjects([
      makeProject({ id: "a", name: "A" }),
      makeProject({ id: "b", name: "B" }),
    ]);
    const rows = container.querySelectorAll("[class*='projectRow']");
    for (const row of Array.from(rows)) {
      expect(row.querySelector(".lucide-wrench")).toBeNull();
    }
  });
});
