import { useState } from "react";
import { CircleDollarSignIcon, FileTextIcon, FlaskConicalIcon, WrenchIcon } from "lucide-react";
import { SystemPromptModal } from "@/modals/SystemPromptModal";
import { TokenCostModal } from "@/modals/TokenCostModal";
import { SkillsModal } from "@/modals/SkillsModal";
import { ToolsModal } from "@/tools/ToolsModal";
import { useTokenTotals, useChildSessionCosts, useSkills, useTools, useSystemPrompt } from "./useSessionInfoBar";
import styles from "@/layout/RightSidebar/RightSidebar.module.css";

export function SkillsButton() {
  const { modalOpen, skills, totalCount, activated, handleOpen, handleClose } = useSkills();

  return (
    <>
      <button className={styles.bottomBtn} onClick={handleOpen}>
        <FlaskConicalIcon className={styles.moduleIcon} />
        {activated.length > 0 ? (
          <span className={styles.skillsBtnContent}>
            <span className={styles.skillsBadges}>
              {activated.map((id) => (
                <span key={id} className={styles.skillBadge}>{id}</span>
              ))}
            </span>
            <span className={styles.skillsCount}>{activated.length}/{totalCount}</span>
          </span>
        ) : (
          <span>Skills ({totalCount})</span>
        )}
      </button>
      {modalOpen && <SkillsModal skills={skills} activated={activated} onClose={handleClose} />}
    </>
  );
}

export function ToolsButton() {
  const { modalOpen, tools, toolCount, tokenEstimate, formatCount, handleOpen, handleClose } = useTools();

  return (
    <>
      <button className={styles.bottomBtn} onClick={handleOpen}>
        <WrenchIcon className={styles.moduleIcon} />
        <span>Commands ({toolCount}, ~{formatCount(tokenEstimate)} tok)</span>
      </button>
      {modalOpen && (
        <ToolsModal tools={tools} onClose={handleClose} />
      )}
    </>
  );
}

export function TokenCostSummary() {
  const [modalOpen, setModalOpen] = useState(false);
  const totals = useTokenTotals();
  const { childCosts, totalChildCost } = useChildSessionCosts();

  const formatDollars = (n: number) =>
    n < 0.01 && n > 0 ? "<$0.01" : `$${n.toFixed(2)}`;

  return (
    <>
      <button className={styles.bottomBtn} onClick={() => setModalOpen(true)}>
        <CircleDollarSignIcon className={styles.moduleIcon} />
        <span>
          Session cost: {formatDollars(totals.totalCost)}
          {totalChildCost > 0 && (
            <span style={{ color: "var(--color-text-tertiary)" }}>
              {" "}(+{formatDollars(totalChildCost)})
            </span>
          )}
        </span>
      </button>
      {modalOpen && (
        <TokenCostModal totals={totals} childCosts={childCosts} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}

export function SystemPromptButton() {
  const { modalOpen, parts, totalTokens, formatCount, handleOpen, handleClose } = useSystemPrompt();

  return (
    <>
      <button className={styles.bottomBtn} onClick={handleOpen}>
        <FileTextIcon className={styles.moduleIcon} />
        <span>System Prompt (~{formatCount(totalTokens)} tok)</span>
      </button>
      {modalOpen && (
        <SystemPromptModal
          parts={parts}
          totalTokens={totalTokens}
          onClose={handleClose}
        />
      )}
    </>
  );
}
