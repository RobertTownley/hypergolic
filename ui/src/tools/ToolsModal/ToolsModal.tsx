import { ChevronDownIcon, ChevronRightIcon, WrenchIcon } from "lucide-react";
import type { ToolInfo } from "@/types/api";
import { Modal } from "@/shared/components/Modal";
import { ToolRow } from "./ToolRow";
import { useToolsModal } from "./useToolsModal";
import styles from "./ToolsModal.module.css";

interface ToolsModalProps {
  tools: ToolInfo[];
  onClose: () => void;
}

export function ToolsModal({ tools, onClose }: ToolsModalProps) {
  const {
    expandedTools,
    collapsedGroups,
    groups,
    toggleTool,
    toggleGroup,
  } = useToolsModal({ tools });

  return (
    <Modal
      onClose={onClose}
      title={`Commands (${tools.length})`}
      icon={<WrenchIcon />}
      width={800}
      maxHeight="80vh"
    >
      <div className={styles.toolsBody}>
        {groups.map((group) => (
          <div key={group.key} className={styles.group}>
            <div className={styles.groupHeader} onClick={() => toggleGroup(group.key)}>
              <span className={styles.groupExpand}>
                {collapsedGroups.has(group.key) ? <ChevronRightIcon /> : <ChevronDownIcon />}
              </span>
              <span className={styles.groupIcon}>
                {group.icon}
              </span>
              <span className={styles.groupLabel}>{group.label}</span>
              <span className={styles.groupCount}>{group.tools.length}</span>
            </div>
            {!collapsedGroups.has(group.key) && (
              <div className={styles.groupTools}>
                {group.tools.map((tool) => (
                  <ToolRow
                    key={tool.id}
                    tool={tool}
                    expanded={expandedTools.has(tool.id)}
                    onToggle={() => toggleTool(tool.id)}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </Modal>
  );
}
