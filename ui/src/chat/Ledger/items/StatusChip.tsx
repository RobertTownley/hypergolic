import { Chip } from "@/shared/components";
import { useLedgerContext } from "../LedgerContext";
import type { LedgerCall } from "../ledgerModel";
import { Elapsed } from "./Elapsed";
import styles from "./items.module.css";

export const STATUS: Record<LedgerCall["status"], { chip: "ok" | "error" | "warning"; label: string }> = {
  ok: { chip: "ok", label: "exit 0" },
  error: { chip: "error", label: "exit 1" },
  pending: { chip: "warning", label: "running" },
};

/** How a call ended — or, while pending, whether it is still being written or already running. */
export function StatusChip({ call, dots = false }: { call: LedgerCall; dots?: boolean }) {
  const status = STATUS[call.status];
  const { live } = useLedgerContext();
  const pending = call.status === "pending";
  // Outside a live turn a pending call was interrupted; its clock would only grow.
  const since = pending && live && Number.isFinite(call.startedAt) ? call.startedAt : undefined;
  return (
    <Chip tone={status.chip}>
      {pending && call.writing ? "writing" : status.label}
      {since !== undefined && <Elapsed since={since} />}
      {pending && dots && <span className={styles.dots}> ●●●</span>}
    </Chip>
  );
}
