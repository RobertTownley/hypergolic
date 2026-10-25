import { useState } from "react";
import { GaugeIcon } from "lucide-react";
import { EmptyState } from "@/shared/components/EmptyState";
import { PanelBody } from "@/shared/components/Panel";
import { Select } from "@/shared/components/Select";
import { Spinner } from "@/shared/components/Spinner";
import { ProgramTable, SessionTable } from "./CostTables";
import { formatAxisNumber, formatBytes } from "./format";
import { PerfCards } from "./PerfCards";
import { StackedChart } from "./StackedChart";
import { usePerformance } from "./usePerformance";
import styles from "../AnalyticsPanel.module.css";

const WINDOWS = [
  { label: "Last 15 minutes", value: 15 },
  { label: "Last hour", value: 60 },
  { label: "Last 6 hours", value: 360 },
  { label: "Last 24 hours", value: 1440 },
];

export function PerformanceView() {
  const [minutes, setMinutes] = useState(60);
  const { report, error } = usePerformance(minutes);
  return (
    <>
      <div className={styles.filters}>
        <Select className={styles.filterSelect} aria-label="Window" value={minutes}
          onChange={setMinutes} options={WINDOWS} />
      </div>
      <PanelBody scrollable className={styles.content}>
        {error && <div className={styles.error}>{error}</div>}
        {!report && !error && <Spinner centered />}
        {report?.available && report.cards && (
          <>
            <PerfCards data={report.cards} />
            <div className={styles.chartsGrid}>
              <StackedChart title="Sandbox CPU by container (cores)" data={report.cpu_by_container} format={formatAxisNumber} />
              <StackedChart title="Sandbox memory by container" data={report.memory_by_container} format={formatBytes} />
            </div>
            <div className={styles.tablesGrid}>
              <SessionTable rows={report.sessions} />
              <ProgramTable rows={report.programs} />
            </div>
          </>
        )}
        {report && !report.available && !error && (
          <EmptyState icon={<GaugeIcon />} text="No telemetry" className={styles.emptyState} />
        )}
      </PanelBody>
    </>
  );
}
