import { Select } from "@/shared/components/Select";
import { ChartColumnIcon } from "lucide-react";
import { EmptyState } from "@/shared/components/EmptyState";
import { PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import { DATE_RANGES } from "./constants";
import { SummaryCards } from "./SummaryCards";
import { CostChart } from "./CostChart";
import { TokensChart } from "./TokensChart";
import { SessionsChart } from "./SessionsChart";
import { ToolUsageSection } from "./ToolUsageSection";
import { useAnalyticsData } from "./useAnalyticsData";
import styles from "./AnalyticsPanel.module.css";

export function UsageView() {
  const {
    projectId,
    setProjectId,
    days,
    setDays,
    loading,
    error,
    summary,
    timeseries,
    tools,
    projectOptions,
  } = useAnalyticsData();

  return (
    <>
      <div className={styles.filters}>
        <Select
          className={styles.filterSelect}
          aria-label="Project"
          value={projectId ?? ""}
          onChange={(val) => setProjectId(val || undefined)}
          options={projectOptions}
        />
        <Select
          className={styles.filterSelect}
          aria-label="Date range"
          value={days}
          onChange={setDays}
          options={DATE_RANGES}
        />
      </div>
      <PanelBody scrollable className={styles.content}>
        {loading && <Spinner centered />}
        {error && <div className={styles.error}>{error}</div>}
        {!loading && !error && summary && (
          <>
            <SummaryCards data={summary} />
            {timeseries.length > 0 ? (
              <>
                <div className={styles.chartsGrid}>
                  <CostChart data={timeseries} />
                  <TokensChart data={timeseries} />
                </div>
                <div className={styles.chartsGrid}>
                  <SessionsChart data={timeseries} />
                  <ToolUsageSection data={tools} />
                </div>
              </>
            ) : (
              <EmptyState
                icon={<ChartColumnIcon />}
                text="No data for the selected period"
                className={styles.emptyState}
              />
            )}
          </>
        )}
      </PanelBody>
    </>
  );
}
