import type { ActionReducerMapBuilder, AsyncThunk } from "@reduxjs/toolkit";

/** Per-key fetch state. SWR semantics: `data` survives refetches and failures. */
export interface AsyncEntry<T> {
  data: T;
  loading: boolean;
  /** True once any fetch has succeeded; distinguishes "empty" from "never loaded". */
  loaded: boolean;
  error: string | null;
}

export function asyncEntry<T>(data: T): AsyncEntry<T> {
  return { data, loading: false, loaded: false, error: null };
}

interface KeyedSpec<S, Ret, Arg, T> {
  /** Return the entry to mutate, creating it if absent (runs inside immer). */
  entry: (state: S, key: string) => AsyncEntry<T>;
  key: (arg: Arg) => string;
  data: (payload: Ret) => T;
  failMessage: string;
}

/** Register pending/fulfilled/rejected for a thunk caching into keyed AsyncEntry state. */
export function addKeyedCases<S, Ret, Arg, T>(
  builder: ActionReducerMapBuilder<S>,
  thunk: AsyncThunk<Ret, Arg, object>,
  spec: KeyedSpec<S, Ret, Arg, T>,
): void {
  builder
    .addCase(thunk.pending, (state, action) => {
      const e = spec.entry(state as unknown as S, spec.key(action.meta.arg));
      e.loading = true;
      e.error = null;
    })
    .addCase(thunk.fulfilled, (state, action) => {
      const e = spec.entry(state as unknown as S, spec.key(action.meta.arg));
      e.data = spec.data(action.payload) as typeof e.data;
      e.loading = false;
      e.loaded = true;
      e.error = null;
    })
    .addCase(thunk.rejected, (state, action) => {
      const e = spec.entry(state as unknown as S, spec.key(action.meta.arg));
      e.loading = false;
      e.error = action.error.message ?? spec.failMessage;
    });
}
