import { Tooltip } from "@/shared/components/Tooltip";
import { Text } from "@/shared/components/Text";
import { PlusIcon, XIcon } from "lucide-react";
import styles from "./SelectionBar.module.css";

interface SelectionBarProps {
  label: string;
  onAttach?: () => void;
  onClear: () => void;
}

export function SelectionBar({ label, onAttach, onClear }: SelectionBarProps) {
  return (
    <div className={styles.selectionBar}>
      <Text className={styles.selectionInfo}>{label}</Text>
      <div className={styles.selectionActions}>
        {onAttach && (
          <Tooltip title="Attach to message">
            <button className={styles.selectionBtn} onClick={onAttach}>
              <PlusIcon /> Attach
            </button>
          </Tooltip>
        )}
        <button className={styles.selectionClearBtn} onClick={onClear}>
          <XIcon />
        </button>
      </div>
    </div>
  );
}
