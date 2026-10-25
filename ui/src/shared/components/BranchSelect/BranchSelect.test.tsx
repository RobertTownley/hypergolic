import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import type { ComponentProps } from "react";
import { BranchSelect } from "./BranchSelect";

vi.mock("lucide-react", () => ({
  GitBranchIcon: () => <span data-testid="branches-icon" />,
  ChevronDownIcon: () => <span data-testid="caret-icon" />,
  LoaderCircleIcon: () => <span data-testid="loading-icon" />,
  PlusIcon: () => <span data-testid="plus-icon" />,
}));

function renderSelect(props: Partial<ComponentProps<typeof BranchSelect>> = {}) {
  return render(
    <BranchSelect branches={["main", "dev"]} value="main" onSelect={() => {}} {...props} />,
  );
}

const openDropdown = () => fireEvent.click(screen.getByRole("button", { name: /main/i }));

describe("BranchSelect", () => {
  it("renders the currently selected branch", () => {
    renderSelect();
    expect(screen.getByText("main")).toBeInTheDocument();
  });

  it("renders placeholder when value is null", () => {
    renderSelect({ value: null, placeholder: "Pick one" });
    expect(screen.getByText("Pick one")).toBeInTheDocument();
  });

  it("shows a loading indicator instead of the value while loading", () => {
    renderSelect({ loading: true });
    expect(screen.getByTestId("loading-icon")).toBeInTheDocument();
    expect(screen.queryByText("main")).not.toBeInTheDocument();
  });

  it("opens the dropdown and lists branches other than the current one", () => {
    renderSelect({ branches: ["main", "dev", "feature/x"] });
    openDropdown();
    expect(screen.getByText("dev")).toBeInTheDocument();
    expect(screen.getByText("feature/x")).toBeInTheDocument();
  });

  it("calls onSelect and closes when a branch is clicked", () => {
    const onSelect = vi.fn();
    renderSelect({ onSelect });
    openDropdown();
    fireEvent.click(screen.getByText("dev"));
    expect(onSelect).toHaveBeenCalledWith("dev");
    expect(screen.queryByText("dev")).not.toBeInTheDocument();
  });

  it("filters branches using the search input", () => {
    renderSelect({ branches: ["main", "dev", "feature/x", "feature/y"] });
    openDropdown();
    fireEvent.change(screen.getByPlaceholderText(/filter/i), { target: { value: "feat" } });
    expect(screen.getByText("feature/x")).toBeInTheDocument();
    expect(screen.getByText("feature/y")).toBeInTheDocument();
    expect(screen.queryByText("dev")).not.toBeInTheDocument();
  });

  it("offers a New Branch affordance when onCreate is provided", () => {
    const onCreate = vi.fn();
    renderSelect({ branches: ["main"], onCreate });
    openDropdown();
    fireEvent.click(screen.getByText("New branch"));
    const input = screen.getByPlaceholderText("branch-name");
    fireEvent.change(input, { target: { value: "topic/foo" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onCreate).toHaveBeenCalledWith("topic/foo");
  });

  it("hides the New Branch affordance when no onCreate is given", () => {
    renderSelect();
    openDropdown();
    expect(screen.queryByText("New branch")).not.toBeInTheDocument();
  });
});
