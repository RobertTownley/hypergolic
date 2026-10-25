import { describe, it, expect, vi, beforeEach } from "vitest";
import { makeSliceStore, pending, fulfilled, rejected } from "@/test/store";
import analyticsReducer, { loadAnalytics, setProjectId } from "./analyticsSlice";
import {
  fetchAnalyticsSummary,
  fetchAnalyticsTimeseries,
  fetchAnalyticsTools,
} from "@/api/analytics";

vi.mock("@/api/analytics", () => ({
  fetchAnalyticsSummary: vi.fn(),
  fetchAnalyticsTimeseries: vi.fn(),
  fetchAnalyticsTools: vi.fn(),
}));

const initialState = {
  projectId: undefined as string | undefined,
  days: 30,
  loading: false,
  error: null as string | null,
  summary: null,
  timeseries: [],
  tools: [],
  lastQuery: null,
};

const sampleSummary = {
  total_sessions: 5,
  total_messages: 42,
  total_cost: 1.23,
  total_input_tokens: 1000,
  total_output_tokens: 2000,
  total_cache_write_tokens: 300,
  total_cache_read_tokens: 400,
};

const samplePoint = {
  period: "2026-08-01",
  sessions: 2,
  messages: 10,
  cost: 0.5,
  input_tokens: 100,
  output_tokens: 200,
  cache_write_tokens: 30,
  cache_read_tokens: 40,
};

const sampleTool = { tool_name: "Bash", count: 7 };

const makeStore = () => makeSliceStore({ analytics: analyticsReducer });

describe("analyticsSlice", () => {
  it("should return the initial state", () => {
    expect(analyticsReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  describe("setProjectId", () => {
    it("should clear the project id", () => {
      const withProject = { ...initialState, projectId: "p1" };
      const state = analyticsReducer(withProject, setProjectId(undefined));
      expect(state.projectId).toBeUndefined();
    });
  });

  describe("loadAnalytics", () => {
    it("should set loading and record the query on pending", () => {
      const action = pending(loadAnalytics, { projectId: "p1", days: 7 });
      const errored = { ...initialState, error: "old error" };
      const state = analyticsReducer(errored, action);
      expect(state.loading).toBe(true);
      expect(state.error).toBeNull();
      expect(state.lastQuery).toEqual({ projectId: "p1", days: 7 });
    });

    it("should store results and the query they describe on fulfilled", () => {
      const action = fulfilled(
        loadAnalytics,
        { summary: sampleSummary, timeseries: [samplePoint], tools: [sampleTool] },
        { projectId: "p1", days: 7 },
      );
      const loading = { ...initialState, loading: true };
      const state = analyticsReducer(loading, action);
      expect(state.loading).toBe(false);
      expect(state.summary).toEqual(sampleSummary);
      expect(state.timeseries).toEqual([samplePoint]);
      expect(state.tools).toEqual([sampleTool]);
      expect(state.lastQuery).toEqual({ projectId: "p1", days: 7 });
    });

    it("should set error and clear the query on rejected", () => {
      const action = rejected(loadAnalytics, "boom");
      const loading = {
        ...initialState,
        loading: true,
        lastQuery: { projectId: "p1", days: 7 },
      };
      const state = analyticsReducer(loading, action);
      expect(state.loading).toBe(false);
      expect(state.error).toBe("boom");
      expect(state.lastQuery).toBeNull();
    });

    it("should fall back to a default error message on rejected", () => {
      const action = rejected(loadAnalytics);
      const state = analyticsReducer({ ...initialState, loading: true }, action);
      expect(state.error).toBe("Failed to load analytics");
    });
  });

  describe("loadAnalytics condition", () => {
    beforeEach(() => {
      vi.mocked(fetchAnalyticsSummary).mockReset().mockResolvedValue(sampleSummary);
      vi.mocked(fetchAnalyticsTimeseries).mockReset().mockResolvedValue([samplePoint]);
      vi.mocked(fetchAnalyticsTools).mockReset().mockResolvedValue([sampleTool]);
    });

    it("should skip a re-dispatch for the query already loaded (remount)", async () => {
      const store = makeStore();
      await store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(1);

      // Simulate the panel remounting with unchanged params.
      await store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(1);
      expect(store.getState().analytics.summary).toEqual(sampleSummary);
    });

    it("should fetch again when the params change", async () => {
      const store = makeStore();
      await store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      await store.dispatch(loadAnalytics({ projectId: "p2", days: 7 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(2);

      await store.dispatch(loadAnalytics({ projectId: "p2", days: 90 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(3);
    });

    it("should dedupe a concurrent dispatch of the same query", async () => {
      let resolve!: (v: typeof sampleSummary) => void;
      vi.mocked(fetchAnalyticsSummary).mockReturnValue(
        new Promise((r) => {
          resolve = r;
        }),
      );

      const store = makeStore();
      const p1 = store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      const p2 = store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));

      resolve(sampleSummary);
      await p1;
      await p2;

      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(1);
    });

    it("should allow a retry after a rejection", async () => {
      vi.mocked(fetchAnalyticsSummary)
        .mockRejectedValueOnce(new Error("fail"))
        .mockResolvedValueOnce(sampleSummary);

      const store = makeStore();
      await store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      expect(store.getState().analytics.error).toBe("fail");

      await store.dispatch(loadAnalytics({ projectId: "p1", days: 7 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledTimes(2);
      expect(store.getState().analytics.summary).toEqual(sampleSummary);
    });

    it("should pass undefined days and month granularity for the all-time range", async () => {
      const store = makeStore();
      await store.dispatch(loadAnalytics({ projectId: undefined, days: -1 }));
      expect(fetchAnalyticsSummary).toHaveBeenCalledWith(undefined, undefined);
      expect(fetchAnalyticsTimeseries).toHaveBeenCalledWith(undefined, undefined, "month");
      expect(fetchAnalyticsTools).toHaveBeenCalledWith(undefined, undefined);
    });
  });
});
