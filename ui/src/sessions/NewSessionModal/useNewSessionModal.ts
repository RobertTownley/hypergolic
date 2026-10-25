import React, { useCallback, useEffect, useState } from "react";
import type { ModelTier } from "@/types/api";
import { useOnChange } from "@/hooks/useOnChange";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveProjectId } from "@/store/selectors";
import { selectDefaultModelTier } from "@/store/uiSlice";
import {
  loadProjectBranches,
  loadProjectRoles,
  selectProjectBranches,
  selectProjectRoles,
} from "@/store/projectsSlice";

const MODEL_TIERS: { value: ModelTier; label: string; shortcut: string }[] = [
  { value: "Low", label: "Low", shortcut: "1" },
  { value: "Medium", label: "Medium", shortcut: "2" },
  { value: "High", label: "High", shortcut: "3" },
  { value: "Extra High", label: "Extra High", shortcut: "4" },
];

const PROJECT_SHORTCUTS = "qwert";
const ROLE_SHORTCUTS = "asdfg";

export { MODEL_TIERS, PROJECT_SHORTCUTS, ROLE_SHORTCUTS };

export function useNewSessionModal(
  onCreate: (
    projectId: string,
    baseBranch: string,
    modelTier: ModelTier,
    role: string,
  ) => void,
) {
  const dispatch = useAppDispatch();
  const projects = useAppSelector((s) => s.projects);
  const activeProjectId = useAppSelector(selectActiveProjectId);
  const defaultModelTier = useAppSelector(selectDefaultModelTier);

  const [projectOverride, setProjectOverride] = useState<string | null>(null);
  const selectedProjectId = projectOverride ?? activeProjectId ?? "";
  const [tierOverride, setTierOverride] = useState<ModelTier | null>(null);
  const modelTier = tierOverride ?? defaultModelTier;

  const [role, setRole] = useState("generalist");
  const [baseBranchOverride, setBaseBranchOverride] = useState<string | null>(null);

  const projectBranches = useAppSelector((s) => selectProjectBranches(s, selectedProjectId));
  const projectRoles = useAppSelector((s) => selectProjectRoles(s, selectedProjectId));

  useEffect(() => {
    if (!selectedProjectId) return;
    void dispatch(loadProjectRoles({ projectId: selectedProjectId }));
    void dispatch(loadProjectBranches({ projectId: selectedProjectId }));
  }, [dispatch, selectedProjectId]);

  useOnChange(selectedProjectId, () => {
    setRole("generalist");
    setBaseBranchOverride(null);
  });

  const branches = projectBranches.data.branches;
  const branchesLoading = projectBranches.loading;
  const baseBranch = baseBranchOverride ?? projectBranches.data.current ?? branches[0] ?? "";

  const projectOptions = projects.ids.map((id: string) => ({
    value: id,
    label: projects.entities[id]?.name ?? id,
  }));

  const roleOptions = projectRoles.data.map((r) => ({
    value: r.id,
    label: r.name,
  }));

  const canSubmit = Boolean(selectedProjectId) && Boolean(baseBranch);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "Enter" && canSubmit) {
        e.preventDefault();
        onCreate(selectedProjectId, baseBranch, modelTier, role);
        return;
      }
      const key = e.key.toLowerCase();
      const tierMatch = MODEL_TIERS.find((t) => t.shortcut === key);
      if (tierMatch) { e.preventDefault(); setTierOverride(tierMatch.value); return; }
      if (key === "q" || key === "w" || key === "e" || key === "r" || key === "t") {
        e.preventDefault();
        const idx = PROJECT_SHORTCUTS.indexOf(key);
        if (idx < projectOptions.length) setProjectOverride(projectOptions[idx].value);
        return;
      }
      if (key === "a" || key === "s" || key === "d" || key === "f" || key === "g") {
        e.preventDefault();
        const idx = ROLE_SHORTCUTS.indexOf(key);
        if (idx < roleOptions.length) setRole(roleOptions[idx].value);
        return;
      }
    },
    [selectedProjectId, baseBranch, canSubmit, modelTier, role, onCreate, projectOptions, roleOptions],
  );

  return {
    selectedProjectId, setSelectedProjectId: setProjectOverride,
    modelTier, setModelTier: setTierOverride,
    role, setRole,
    baseBranch, setBaseBranch: setBaseBranchOverride,
    branches, branchesLoading,
    projectOptions, roleOptions,
    canSubmit,
    handleKeyDown,
  };
}
