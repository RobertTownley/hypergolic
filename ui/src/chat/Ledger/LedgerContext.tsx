import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import type { LedgerCall } from "./ledgerModel";

interface LedgerContextValue {
  /** The scroll container, for whole-transcript screenshots. */
  viewportRef: RefObject<HTMLDivElement | null>;
  /** The session's turn is in flight, so its pending calls are really pending. */
  live: boolean;
  /** The call open in the inspector, if any. */
  inspected: LedgerCall | null;
  inspect: (call: LedgerCall) => void;
  /** Open the call, or close the inspector if it is already the one shown. */
  toggleInspect: (call: LedgerCall) => void;
  closeInspector: () => void;
}

const LedgerContext = createContext<LedgerContextValue | null>(null);

/**
 * Holds the one piece of ledger state that outlives a single row: which call
 * the docked inspector is showing. Cards deep in the transcript open it
 * without the transcript owning a modal.
 */
export function LedgerProvider({
  viewportRef,
  live = false,
  children,
}: {
  viewportRef: RefObject<HTMLDivElement | null>;
  /** The session's turn is in flight. Pending calls outside one were interrupted. */
  live?: boolean;
  children: ReactNode;
}) {
  const [inspected, setInspected] = useState<LedgerCall | null>(null);
  const inspect = useCallback((call: LedgerCall) => setInspected(call), []);
  const toggleInspect = useCallback(
    (call: LedgerCall) => setInspected((open) => (open?.id === call.id ? null : call)),
    [],
  );
  const closeInspector = useCallback(() => setInspected(null), []);
  const value = useMemo(
    () => ({ viewportRef, live, inspected, inspect, toggleInspect, closeInspector }),
    [viewportRef, live, inspected, inspect, toggleInspect, closeInspector],
  );
  return <LedgerContext.Provider value={value}>{children}</LedgerContext.Provider>;
}

/**
 * Keeps an open inspector on the call it was opened from as that call changes:
 * inspect a running command and the result landing rebuilds the ledger into a
 * new object, which the inspector would otherwise never see.
 */
export function useInspectorSync(call: LedgerCall) {
  const { inspected, inspect } = useLedgerContext();
  useEffect(() => {
    if (inspected && inspected.id === call.id && inspected !== call) inspect(call);
  }, [call, inspected, inspect]);
}

export function useLedgerContext() {
  const ctx = use(LedgerContext);
  if (!ctx) throw new Error("useLedgerContext must be used inside LedgerProvider");
  return ctx;
}
