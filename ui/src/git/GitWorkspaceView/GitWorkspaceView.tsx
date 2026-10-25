import { useState } from "react";
import { FileDiffIcon, HistoryIcon } from "lucide-react";
import { useOnChange } from "@/hooks/useOnChange";
import { useAppSelector } from "@/store";
import { selectActiveSession, selectActiveWorkspace, selectDiffMode } from "@/store/selectors";
import { Panel } from "@/shared/components/Panel";
import { GitLogList } from "@/git/GitLog";
import { InlineChanges } from "./InlineChanges";
import styles from "./GitWorkspaceView.module.css";

type Tab = "history" | "diff";

export function GitWorkspaceView() {
  const { status } = useAppSelector(selectActiveWorkspace);
  const diffMode = useAppSelector(selectDiffMode);
  const baseBranch = useAppSelector(selectActiveSession)?.base_branch ?? null;
  const mode = baseBranch ? diffMode : "uncommitted";
  const hasChanges =
    !!status &&
    (mode === "all"
      ? (status.all_changes?.length ?? 0) > 0
      : status.staged.length + status.unstaged.length + status.untracked.length > 0);

  const autoTab: Tab = hasChanges ? "diff" : "history";
  const [tab, setTab] = useState<Tab>(autoTab);
  useOnChange(hasChanges, () => setTab(autoTab));

  return (
    <Panel>
      <div className={styles.tabBar} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "history"}
          className={tab === "history" ? styles.tabActive : styles.tab}
          onClick={() => setTab("history")}
        >
          <HistoryIcon /> History
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "diff"}
          className={tab === "diff" ? styles.tabActive : styles.tab}
          onClick={() => setTab("diff")}
        >
          <FileDiffIcon /> Diff
        </button>
      </div>
      {tab === "history" ? <GitLogList /> : <InlineChanges mode={mode} />}
    </Panel>
  );
}
