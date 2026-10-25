import { CircleDollarSignIcon } from "lucide-react";
import { Badge } from "@/shared/components/Badge";
import { Modal } from "@/shared/components/Modal";
import styles from "./TokenCostModal.module.css";
import { formatTokens } from "@/shared/formatTokens";

export interface TokenTotals {
  inputTokens: number;
  outputTokens: number;
  cacheCreation: number;
  cacheRead: number;
  inputCost: number;
  outputCost: number;
  cacheWriteCost: number;
  cacheReadCost: number;
  totalCost: number;
  modelTier: string;
}

export interface ChildSessionCost {
  sessionId: string;
  modelTier: string;
  totals: TokenTotals;
}

interface TokenCostModalProps {
  totals: TokenTotals;
  childCosts?: ChildSessionCost[];
  onClose: () => void;
}

function formatDollars(n: number) {
  if (n === 0) return "$0.00";
  if (n < 0.001) return "<$0.001";
  if (n < 0.01) return `$${n.toFixed(3)}`;
  return `$${n.toFixed(2)}`;
}

const ROWS: {
  label: string;
  tokenKey: keyof TokenTotals;
  costKey: keyof TokenTotals;
}[] = [
  { label: "Input", tokenKey: "inputTokens", costKey: "inputCost" },
  { label: "Output", tokenKey: "outputTokens", costKey: "outputCost" },
  {
    label: "Cache Write",
    tokenKey: "cacheCreation",
    costKey: "cacheWriteCost",
  },
  { label: "Cache Read", tokenKey: "cacheRead", costKey: "cacheReadCost" },
];

export function TokenCostModal({ totals, childCosts, onClose }: TokenCostModalProps) {
  const hasChildren = childCosts && childCosts.length > 0;
  const childrenTotal = hasChildren
    ? childCosts.reduce((sum, c) => sum + c.totals.totalCost, 0)
    : 0;

  return (
    <Modal
      onClose={onClose}
      title="Token Usage &amp; Cost"
      icon={<CircleDollarSignIcon />}
      width={420}
      badge={
        <Badge variant="primary" uppercase>
          Model Tier: {totals.modelTier}
        </Badge>
      }
    >
      <div className={styles.tableWrapper}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Category</th>
              <th className={styles.thRight}>Tokens</th>
              <th className={styles.thRight}>Cost</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.label} className={styles.row}>
                <td className={styles.td}>{row.label}</td>
                <td className={styles.tdRight}>
                  {formatTokens(totals[row.tokenKey] as number)}
                </td>
                <td className={styles.tdRight}>
                  {formatDollars(totals[row.costKey] as number)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className={styles.totalRow}>
              <td className={styles.td}>Total</td>
              <td className={styles.tdRight}></td>
              <td className={styles.tdRight}>
                {formatDollars(totals.totalCost)}
              </td>
            </tr>
          </tfoot>
        </table>

        {hasChildren && (
          <div className={styles.childSection}>
            <div className={styles.childSectionHeader}>Child Sessions</div>
            {childCosts.map((child) => (
              <div key={child.sessionId} className={styles.childRow}>
                <span className={styles.childLabel}>
                  {child.sessionId.slice(0, 8)}
                  <span className={styles.childTier}>{child.modelTier}</span>
                </span>
                <span className={styles.childCost}>
                  {formatDollars(child.totals.totalCost)}
                </span>
              </div>
            ))}
            <div className={styles.childTotalRow}>
              <span>Children Total</span>
              <span className={styles.childCost}>
                {formatDollars(childrenTotal)}
              </span>
            </div>
            <div className={styles.combinedTotalRow}>
              <span>Combined Total</span>
              <span className={styles.childCost}>
                {formatDollars(totals.totalCost + childrenTotal)}
              </span>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}
