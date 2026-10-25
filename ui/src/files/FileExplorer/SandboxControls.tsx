import type { SandboxContainer, SandboxRoot } from "@/types/api";
import { SandboxSelect } from "./SandboxSelect";
import styles from "./FileExplorer.module.css";

interface SandboxControlsProps {
  containers: SandboxContainer[];
  container: string | null;
  roots: SandboxRoot[];
  root: string | null;
  onSelectContainer: (id: string) => void;
  onSelectRoot: (id: string) => void;
}

export function SandboxControls({
  containers,
  container,
  roots,
  root,
  onSelectContainer,
  onSelectRoot,
}: SandboxControlsProps) {
  return (
    <div className={styles.sandboxControls}>
      <SandboxSelect
        ariaLabel="Container"
        placeholder="Container"
        value={container}
        onChange={onSelectContainer}
        options={containers.map((c) => ({ value: c.id, label: c.id }))}
      />
      <SandboxSelect
        ariaLabel="Root"
        placeholder="Root"
        value={root}
        disabled={roots.length === 0}
        onChange={onSelectRoot}
        options={roots.map((r) => ({ value: r.id, label: r.label }))}
      />
    </div>
  );
}
