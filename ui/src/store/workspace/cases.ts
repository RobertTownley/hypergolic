import type { ActionReducerMapBuilder, AsyncThunk, SerializedError } from "@reduxjs/toolkit";
import type { SessionScopedArg } from "@/store/workspaceThunks";
import { writeToSlot, type SessionWorkspace, type WorkspaceState } from "@/store/workspace/state";

type BoolKey = {
  [K in keyof SessionWorkspace]: SessionWorkspace[K] extends boolean ? K : never;
}[keyof SessionWorkspace];

interface ScopedSpec<R, A extends SessionScopedArg> {
  loading: BoolKey;
  /** Where fulfilled writes land: the response's session_id (default) or the request arg's. */
  fulfilledId?: "payload" | "arg";
  onPending?: (slot: SessionWorkspace, arg: A) => void;
  onFulfilled: (slot: SessionWorkspace, payload: R, arg: A) => void;
  /** [error field, fallback message]; omitted = failures only clear the loading flag. */
  error?: [keyof SessionWorkspace & string, string];
  /** Discard a fulfilled payload (loading still clears) — e.g. a response for
      a repo scope the user has since switched away from. */
  dropFulfilled?: (state: WorkspaceState, payload: R, arg: A) => boolean;
  onRejected?: (slot: SessionWorkspace, error: SerializedError) => void;
}

/** Register pending/fulfilled/rejected for a session-scoped loading thunk. */
export function scopedCases<R, A extends SessionScopedArg>(
  builder: ActionReducerMapBuilder<WorkspaceState>,
  thunk: AsyncThunk<R, A, object>,
  spec: ScopedSpec<R, A>,
): void {
  const set = (slot: SessionWorkspace, key: string, value: unknown) => {
    (slot as unknown as Record<string, unknown>)[key] = value;
  };
  builder
    .addCase(thunk.pending, (state, action) => {
      writeToSlot(state, action.meta.arg.sessionId, (slot) => {
        set(slot, spec.loading, true);
        if (spec.error) set(slot, spec.error[0], null);
        spec.onPending?.(slot, action.meta.arg);
      });
    })
    .addCase(thunk.fulfilled, (state, action) => {
      const sid =
        spec.fulfilledId === "arg"
          ? action.meta.arg.sessionId
          : (action.payload as { session_id: string }).session_id;
      const drop = spec.dropFulfilled?.(state, action.payload, action.meta.arg) ?? false;
      writeToSlot(state, sid, (slot) => {
        set(slot, spec.loading, false);
        if (!drop) spec.onFulfilled(slot, action.payload, action.meta.arg);
      });
    })
    .addCase(thunk.rejected, (state, action) => {
      writeToSlot(state, action.meta.arg.sessionId, (slot) => {
        set(slot, spec.loading, false);
        if (spec.onRejected) spec.onRejected(slot, action.error);
        else if (spec.error) set(slot, spec.error[0], action.error.message ?? spec.error[1]);
      });
    });
}

/** Register cases for a git action driving the global actionLoading/error pair. */
export function actionCases<R, A>(
  builder: ActionReducerMapBuilder<WorkspaceState>,
  thunk: AsyncThunk<R, A, object>,
  failMessage: string,
  onFulfilled: (state: WorkspaceState, payload: R, arg: A) => void,
): void {
  builder
    .addCase(thunk.pending, (state) => {
      state.actionLoading = true;
      state.error = null;
    })
    .addCase(thunk.fulfilled, (state, action) => {
      state.actionLoading = false;
      onFulfilled(state, action.payload, action.meta.arg);
    })
    .addCase(thunk.rejected, (state, action) => {
      state.actionLoading = false;
      state.error = action.error.message ?? failMessage;
    });
}
