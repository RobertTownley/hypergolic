import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import {
  fetchAnalyticsSummary,
  fetchAnalyticsTimeseries,
  fetchAnalyticsTools,
} from "@/api/analytics";
import type { AnalyticsSummary, TimeseriesPoint, ToolCount } from "@/api/analytics";
import { granularityForDays } from "@/analytics/formatters";
import type { RootState } from "@/store";

export interface AnalyticsQuery {
  projectId: string | undefined;
  days: number;
}

interface AnalyticsState {
  projectId: string | undefined;
  days: number;
  loading: boolean;
  error: string | null;
  summary: AnalyticsSummary | null;
  timeseries: TimeseriesPoint[];
  tools: ToolCount[];
  // The query whose outcome the slice currently holds (in flight or loaded).
  // Reset to null on failure so the next mount or param change retries.
  lastQuery: AnalyticsQuery | null;
}

const initialState: AnalyticsState = {
  projectId: undefined,
  days: 30,
  loading: false,
  error: null,
  summary: null,
  timeseries: [],
  tools: [],
  lastQuery: null,
};

export const loadAnalytics = createAsyncThunk(
  "analytics/load",
  async ({ projectId, days }: AnalyticsQuery) => {
    const effectiveDays = days === -1 ? undefined : days;
    const granularity = days === -1 ? "month" : granularityForDays(days);
    const [summary, timeseries, tools] = await Promise.all([
      fetchAnalyticsSummary(projectId, effectiveDays),
      fetchAnalyticsTimeseries(projectId, effectiveDays, granularity),
      fetchAnalyticsTools(projectId, effectiveDays),
    ]);
    return { summary, timeseries, tools };
  },
  {
    // Skip when the slice already holds (or is fetching) this exact query,
    // e.g. on remount with unchanged params after switching tabs away and back.
    condition: ({ projectId, days }, { getState }) => {
      const { lastQuery } = (getState() as { analytics: AnalyticsState }).analytics;
      if (lastQuery && lastQuery.projectId === projectId && lastQuery.days === days) {
        return false;
      }
      return true;
    },
  },
);

const analyticsSlice = createSlice({
  name: "analytics",
  initialState,
  reducers: {
    setProjectId(state, action: PayloadAction<string | undefined>) {
      state.projectId = action.payload;
    },
    setDays(state, action: PayloadAction<number>) {
      state.days = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadAnalytics.pending, (state, action) => {
        state.loading = true;
        state.error = null;
        state.lastQuery = action.meta.arg;
      })
      .addCase(loadAnalytics.fulfilled, (state, action) => {
        state.loading = false;
        state.summary = action.payload.summary;
        state.timeseries = action.payload.timeseries;
        state.tools = action.payload.tools;
        state.lastQuery = action.meta.arg;
      })
      .addCase(loadAnalytics.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message ?? "Failed to load analytics";
        state.lastQuery = null;
      });
  },
});

export const { setProjectId, setDays } = analyticsSlice.actions;

export const selectAnalyticsProjectId = (state: RootState) => state.analytics.projectId;
export const selectAnalyticsDays = (state: RootState) => state.analytics.days;

export default analyticsSlice.reducer;
