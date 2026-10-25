import type { ProgramCost, SessionCost } from "@/api/analytics";
import { Card } from "@/shared/components/Card";
import { formatBytes, formatSeconds } from "./format";
import styles from "../AnalyticsPanel.module.css";

export function SessionTable({ rows }: { rows: SessionCost[] }) {
  return (
    <Card>
      <div className={styles.chartTitle}>Sessions by sandbox CPU</div>
      <table className={styles.table}>
        <thead><tr><th>Session</th><th>State</th><th>CPU</th><th>Memory</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.session_id}>
              <td title={r.session_id}>{r.description ?? r.session_id}</td>
              <td>{r.state}</td>
              <td>{formatSeconds(r.cpu_seconds)}</td>
              <td>{formatBytes(r.memory_bytes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

export function ProgramTable({ rows }: { rows: ProgramCost[] }) {
  return (
    <Card>
      <div className={styles.chartTitle}>Commands by CPU</div>
      <table className={styles.table}>
        <thead><tr><th>Program</th><th>Runs</th><th>Wall</th><th>CPU</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.program}>
              <td>{r.program}</td>
              <td>{r.runs}</td>
              <td>{formatSeconds(r.wall_seconds)}</td>
              <td>{formatSeconds(r.cpu_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
