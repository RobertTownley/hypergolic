import { ZapIcon } from "lucide-react";
import type { ModelTier } from "@/types/api";
import { Modal } from "@/shared/components/Modal";
import { BranchSelect } from "@/shared/components";
import { useNewSessionModal, MODEL_TIERS, PROJECT_SHORTCUTS, ROLE_SHORTCUTS } from "./useNewSessionModal";
import styles from "./NewSessionModal.module.css";

interface OptionItem {
  value: string;
  label: string;
}

interface NewSessionModalProps {
  onClose: () => void;
  onCreate: (projectId: string, baseBranch: string, modelTier: ModelTier, role: string) => void;
}

export function NewSessionModal({ onClose, onCreate }: NewSessionModalProps) {
  const {
    selectedProjectId, setSelectedProjectId,
    modelTier, setModelTier,
    role, setRole,
    baseBranch, setBaseBranch,
    branches, branchesLoading,
    projectOptions, roleOptions,
    canSubmit,
    handleKeyDown,
  } = useNewSessionModal(onCreate);

  return (
    <Modal
      onClose={onClose}
      onKeyDown={handleKeyDown}
      title="New Session"
      icon={<ZapIcon />}
      width={720}
      footer={
        <div className={styles.footerRow}>
          <span className={styles.hint}>
            Base branch:{" "}
            <BranchSelect
              branches={branches}
              value={baseBranch || null}
              onSelect={setBaseBranch}
              loading={branchesLoading}
              placeholder="Select branch"
            />
          </span>
          <span className={styles.hint}>
            Press <kbd className={styles.kbd}>Enter</kbd> to create
          </span>
          <button
            className={styles.createBtn}
            disabled={!canSubmit}
            onClick={() => onCreate(selectedProjectId, baseBranch, modelTier, role)}
          >
            Create Session
          </button>
        </div>
      }
    >
      <div className={styles.columns}>
        <div className={styles.column}>
          <label className={styles.label}>Project</label>
          <div className={styles.optionList}>
            {projectOptions.map((opt: OptionItem, i: number) => (
              <button
                key={opt.value}
                className={`${styles.optionBtn} ${opt.value === selectedProjectId ? styles.active : ""}`}
                onClick={() => setSelectedProjectId(opt.value)}
              >
                {i < PROJECT_SHORTCUTS.length && (
                  <kbd className={styles.kbd}>{PROJECT_SHORTCUTS[i].toUpperCase()}</kbd>
                )}
                <span className={styles.optionLabel}>{opt.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.column}>
          <label className={styles.label}>Model Tier</label>
          <div className={styles.optionList}>
            {MODEL_TIERS.map((tier) => (
              <button
                key={tier.value}
                className={`${styles.optionBtn} ${tier.value === modelTier ? styles.active : ""}`}
                onClick={() => setModelTier(tier.value)}
              >
                <kbd className={styles.kbd}>{tier.shortcut}</kbd>
                <span className={styles.optionLabel}>{tier.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className={styles.column}>
          <label className={styles.label}>Role</label>
          <div className={styles.optionList}>
            {roleOptions.map((opt: OptionItem, i: number) => (
              <button
                key={opt.value}
                className={`${styles.optionBtn} ${opt.value === role ? styles.active : ""}`}
                onClick={() => setRole(opt.value)}
              >
                {i < ROLE_SHORTCUTS.length && (
                  <kbd className={styles.kbd}>{ROLE_SHORTCUTS[i].toUpperCase()}</kbd>
                )}
                <span className={styles.optionLabel}>{opt.label}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
