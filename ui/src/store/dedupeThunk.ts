import type { Middleware } from "@reduxjs/toolkit";

const inFlight = new Set<string>();
const keyFns = new Map<string, (arg: unknown) => string | number | null | undefined>();

function compositeKey(typePrefix: string, arg: unknown): string {
  const fn = keyFns.get(typePrefix);
  const scope = fn ? fn(arg) : null;
  return scope == null || scope === "" ? typePrefix : `${typePrefix}::${scope}`;
}

export function dedupeCondition<Arg>(
  typePrefix: string,
  keyFn?: (arg: Arg) => string | number | null | undefined,
) {
  if (keyFn) {
    keyFns.set(typePrefix, keyFn as (arg: unknown) => string | number | null | undefined);
  }
  return (arg: Arg): boolean | undefined => {
    // Mutation-driven and scope-switch refetches must never be swallowed by
    // an in-flight fetch that may answer for older state.
    if ((arg as { force?: boolean } | undefined)?.force) return undefined;
    const key = compositeKey(typePrefix, arg);
    if (inFlight.has(key)) return false;
    return undefined;
  };
}

export const dedupeTracker: Middleware = () => (next) => (action: unknown) => {
  const a = action as { type?: string; meta?: { arg?: unknown } };
  if (!a.type) return next(action);

  const match = a.type.match(/^(.+)\/(pending|fulfilled|rejected)$/);
  if (!match) return next(action);

  const [, prefix, status] = match;
  const key = compositeKey(prefix, a.meta?.arg);
  if (status === "pending") {
    inFlight.add(key);
  } else {
    inFlight.delete(key);
  }

  return next(action);
};

export function resetDedupeTracking() {
  inFlight.clear();
}

// Test-only escape hatch: clears the keyFn registry so ad-hoc thunks
// registered from other test files don't leak across tests. Production
// code never calls this.
export function resetDedupeKeyFns() {
  keyFns.clear();
}
