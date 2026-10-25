import { configureStore, type Reducer } from "@reduxjs/toolkit";
import { dedupeTracker, resetDedupeTracking } from "@/store/dedupeThunk";

type ThunkLike<A> = ((arg: A) => unknown) & {
  pending: { type: string };
  fulfilled: { type: string };
  rejected: { type: string };
};

/** Slice-scoped store with the dedupe middleware; resets dedupe tracking per store. */
export function makeSliceStore<R extends Record<string, Reducer>>(reducers: R) {
  resetDedupeTracking();
  return configureStore({
    reducer: reducers,
    middleware: (getDefault) => getDefault().concat(dedupeTracker),
  });
}

export function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

// Lifecycle action builders for driving reducers without dispatching real thunks.
export const pending = <A>(thunk: ThunkLike<A>, arg?: A) =>
  ({ type: thunk.pending.type, meta: { arg } });
export const fulfilled = <A, R>(thunk: ThunkLike<A>, payload: R, arg?: A) =>
  ({ type: thunk.fulfilled.type, payload, meta: { arg } });
export const rejected = <A>(thunk: ThunkLike<A>, message?: string, arg?: A) =>
  ({ type: thunk.rejected.type, error: message ? { message } : {}, meta: { arg } });
