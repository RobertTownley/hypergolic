import { describe, it, expect, vi, beforeEach } from "vitest";
import { configureStore, createAsyncThunk, createSlice, type Reducer } from "@reduxjs/toolkit";
import { dedupeCondition, dedupeTracker, resetDedupeTracking } from "./dedupeThunk";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

function makeStore<S>(reducer: Reducer<S>) {
  return configureStore({
    reducer: { test: reducer },
    middleware: (getDefault) => getDefault().concat(dedupeTracker),
  });
}

const mockApi = vi.fn<() => Promise<string>>();

const fetchData = createAsyncThunk(
  "test/fetch",
  async (_arg: void) => mockApi(),
  { condition: dedupeCondition<void>("test/fetch") },
);

const testSlice = createSlice({
  name: "test",
  initialState: { data: null as string | null, loading: false },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchData.pending, (state) => { state.loading = true; })
      .addCase(fetchData.fulfilled, (state, action) => {
        state.loading = false;
        state.data = action.payload;
      })
      .addCase(fetchData.rejected, (state) => { state.loading = false; });
  },
});

describe("dedupeThunk", () => {
  beforeEach(() => {
    mockApi.mockReset();
    resetDedupeTracking();
  });

  it("should allow a single thunk dispatch", async () => {
    mockApi.mockResolvedValue("result");
    const store = makeStore(testSlice.reducer);
    await store.dispatch(fetchData());
    expect(mockApi).toHaveBeenCalledTimes(1);
    expect(store.getState().test.data).toBe("result");
  });

  it("should deduplicate concurrent dispatches of the same thunk", async () => {
    const { promise, resolve } = deferred<string>();
    mockApi.mockReturnValue(promise);

    const store = makeStore(testSlice.reducer);
    const p1 = store.dispatch(fetchData());
    const p2 = store.dispatch(fetchData());

    resolve("done");
    await p1;
    await p2;

    expect(mockApi).toHaveBeenCalledTimes(1);
  });

  it("should allow dispatch again after the first completes", async () => {
    mockApi.mockResolvedValueOnce("first").mockResolvedValueOnce("second");
    const store = makeStore(testSlice.reducer);

    await store.dispatch(fetchData());
    expect(mockApi).toHaveBeenCalledTimes(1);

    await store.dispatch(fetchData());
    expect(mockApi).toHaveBeenCalledTimes(2);
    expect(store.getState().test.data).toBe("second");
  });

  it("should allow dispatch again after a rejection", async () => {
    mockApi.mockRejectedValueOnce(new Error("fail")).mockResolvedValueOnce("ok");
    const store = makeStore(testSlice.reducer);

    await store.dispatch(fetchData());
    expect(mockApi).toHaveBeenCalledTimes(1);

    await store.dispatch(fetchData());
    expect(mockApi).toHaveBeenCalledTimes(2);
    expect(store.getState().test.data).toBe("ok");
  });
});

describe("dedupeThunk — session-keyed scope", () => {
  const scopedMock = vi.fn<(sessionId: string) => Promise<string>>();

  interface ScopedArg { sessionId: string }

  const fetchScoped = createAsyncThunk(
    "test/scoped",
    async (arg: ScopedArg) => scopedMock(arg.sessionId),
    { condition: dedupeCondition<ScopedArg>("test/scoped", (arg) => arg.sessionId) },
  );

  const scopedSlice = createSlice({
    name: "scoped",
    initialState: { last: null as string | null },
    reducers: {},
    extraReducers: (builder) => {
      builder.addCase(fetchScoped.fulfilled, (state, action) => {
        state.last = action.payload;
      });
    },
  });

  beforeEach(() => {
    scopedMock.mockReset();
    resetDedupeTracking();
    // Intentionally no resetDedupeKeyFns() — our fetchScoped thunk registers
    // its keyFn at module load. Clearing it here would make the second and
    // subsequent tests run without session-scoped dedup, silently reverting
    // to bare-prefix dedup and breaking the cross-session tests.
  });

  it("dedupes concurrent dispatches for the same session", async () => {
    const { promise, resolve } = deferred<string>();
    scopedMock.mockReturnValue(promise);

    const store = makeStore(scopedSlice.reducer);
    const p1 = store.dispatch(fetchScoped({ sessionId: "A" }));
    const p2 = store.dispatch(fetchScoped({ sessionId: "A" }));

    resolve("A-result");
    await p1;
    await p2;

    expect(scopedMock).toHaveBeenCalledTimes(1);
    expect(scopedMock).toHaveBeenCalledWith("A");
  });

  it("does NOT dedupe concurrent dispatches for different sessions", async () => {
    const a = deferred<string>();
    const b = deferred<string>();
    scopedMock.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);

    const store = makeStore(scopedSlice.reducer);
    const pA = store.dispatch(fetchScoped({ sessionId: "A" }));
    const pB = store.dispatch(fetchScoped({ sessionId: "B" }));

    a.resolve("A");
    b.resolve("B");
    await pA;
    await pB;

    expect(scopedMock).toHaveBeenCalledTimes(2);
    expect(scopedMock).toHaveBeenNthCalledWith(1, "A");
    expect(scopedMock).toHaveBeenNthCalledWith(2, "B");
  });

  it("switch-then-switch-back allows a fresh dispatch for the same session", async () => {
    scopedMock.mockResolvedValueOnce("A1").mockResolvedValueOnce("A2");
    const store = makeStore(scopedSlice.reducer);

    await store.dispatch(fetchScoped({ sessionId: "A" }));
    expect(scopedMock).toHaveBeenCalledTimes(1);

    // Simulate having switched away and back; the prior call completed
    // so the composite key was cleared on fulfilled.
    await store.dispatch(fetchScoped({ sessionId: "A" }));
    expect(scopedMock).toHaveBeenCalledTimes(2);
  });

  it("clears the composite key on rejected", async () => {
    scopedMock.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce("after");
    const store = makeStore(scopedSlice.reducer);

    await store.dispatch(fetchScoped({ sessionId: "A" }));
    await store.dispatch(fetchScoped({ sessionId: "A" }));

    expect(scopedMock).toHaveBeenCalledTimes(2);
  });
});
