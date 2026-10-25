import { useState, type ReactNode } from "react";
import { ChartColumnIcon, GaugeIcon } from "lucide-react";
import { Panel, PanelHeader } from "@/shared/components/Panel";
import { PerformanceView } from "./performance/PerformanceView";
import { UsageView } from "./UsageView";
import styles from "./AnalyticsPanel.module.css";

type Tab = "usage" | "performance";

const TABS: Array<{ id: Tab; label: string; icon: ReactNode }> = [
  { id: "usage", label: "Sessions & Usage", icon: <ChartColumnIcon /> },
  { id: "performance", label: "Performance & Observability", icon: <GaugeIcon /> },
];

export function AnalyticsPanel() {
  const [tab, setTab] = useState<Tab>("usage");
  return (
    <Panel>
      <PanelHeader icon={<ChartColumnIcon />}>Analytics</PanelHeader>
      <div className={styles.tabBar} role="tablist">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id}
            className={tab === t.id ? styles.tabActive : styles.tab} onClick={() => setTab(t.id)}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>
      {tab === "usage" ? <UsageView /> : <PerformanceView />}
    </Panel>
  );
}
