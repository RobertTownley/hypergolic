import { createSelector } from "@reduxjs/toolkit";
import { selectIsSessionStreaming, selectMessagesForSession } from "@/store/selectors";
import { buildLedger } from "./ledgerModel";
import { foldQuietRuns } from "./quietRuns";
import { nestCompactedRuns } from "./turnSummaries";

// Streaming toggles at turn boundaries only, so the view stays stable across deltas.
export const selectLedgerItems = createSelector(
  [selectMessagesForSession, selectIsSessionStreaming],
  (m, live) => foldQuietRuns(nestCompactedRuns(buildLedger(m)), live),
);
