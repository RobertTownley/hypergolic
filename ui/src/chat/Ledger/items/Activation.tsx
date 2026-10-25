import { FlaskConicalIcon } from "lucide-react";
import { useLedgerContext, useInspectorSync } from "../LedgerContext";
import type { LedgerCall } from "../ledgerModel";
import { cx } from "@/utils/cx";
import styles from "./items.module.css";

/** A skill was activated: a divider naming it, with the loaded guidance one click away. */
export function Activation({ skill, call }: { skill: string; call: LedgerCall }) {
  const { toggleInspect, inspected } = useLedgerContext();
  useInspectorSync(call);
  const open = inspected?.id === call.id;
  return (
    <div className={styles.transition}>
      <button
        type="button"
        className={cx(styles.transitionPill, styles.activationPill, open && styles.inspected)}
        aria-pressed={open}
        onClick={() => toggleInspect(call)}
      >
        <FlaskConicalIcon />
        skill <b>{skill}</b>
      </button>
    </div>
  );
}
