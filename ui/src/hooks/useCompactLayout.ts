import { useSyncExternalStore } from "react";

const BREAKPOINT = 1400;

function subscribe(callback: () => void) {
  const mql = window.matchMedia(`(max-width: ${BREAKPOINT}px)`);
  mql.addEventListener("change", callback);
  return () => mql.removeEventListener("change", callback);
}

function getSnapshot() {
  return window.innerWidth <= BREAKPOINT;
}

function getServerSnapshot() {
  return false;
}

export function useCompactLayout() {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
