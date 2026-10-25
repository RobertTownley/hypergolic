import { getJson } from "@/api/http";

const BASE = "/api/analytics";

export interface AnalyticsSummary {
  total_sessions: number;
  total_messages: number;
  total_cost: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cache_write_tokens: number;
  total_cache_read_tokens: number;
}

export interface TimeseriesPoint {
  period: string;
  sessions: number;
  messages: number;
  cost: number;
  input_tokens: number;
  output_tokens: number;
  cache_write_tokens: number;
  cache_read_tokens: number;
}

export interface ToolCount {
  tool_name: string;
  count: number;
}

function buildParams(projectId?: string, days?: number, granularity?: string): string {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  if (days !== undefined) params.set("days", String(days));
  if (granularity) params.set("granularity", granularity);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export async function fetchAnalyticsSummary(projectId?: string, days?: number): Promise<AnalyticsSummary> {
  return getJson(`${BASE}/summary${buildParams(projectId, days)}`, "Failed to fetch analytics summary");
}

export async function fetchAnalyticsTimeseries(
  projectId?: string,
  days?: number,
  granularity?: string,
): Promise<TimeseriesPoint[]> {
  return getJson(`${BASE}/timeseries${buildParams(projectId, days, granularity)}`, "Failed to fetch analytics timeseries");
}

export async function fetchAnalyticsTools(projectId?: string, days?: number): Promise<ToolCount[]> {
  return getJson(`${BASE}/tools${buildParams(projectId, days)}`, "Failed to fetch analytics tools");
}

export interface PerformanceCards {
  sandboxes: number;
  idle_sandboxes: number;
  sandbox_cores: number | null;
  idle_cpu_share: number | null;
  sandbox_memory_bytes: number | null;
  throttled_cores: number | null;
  harness_cores: number | null;
  harness_rss_bytes: number | null;
  loop_lag_p95_s: number | null;
}

export interface SeriesPoint {
  at: number;
  values: Record<string, number>;
}

export interface SessionCost {
  session_id: string;
  description: string | null;
  state: string;
  cpu_seconds: number;
  memory_bytes: number | null;
}

export interface ProgramCost {
  program: string;
  runs: number;
  wall_seconds: number;
  cpu_seconds: number | null;
}

export interface PerformanceReport {
  available: boolean;
  error: string | null;
  cards: PerformanceCards | null;
  cpu_by_container: SeriesPoint[];
  memory_by_container: SeriesPoint[];
  sessions: SessionCost[];
  programs: ProgramCost[];
}

export async function fetchPerformance(minutes: number): Promise<PerformanceReport> {
  return getJson(`${BASE}/performance?minutes=${minutes}`, "Failed to fetch performance");
}
