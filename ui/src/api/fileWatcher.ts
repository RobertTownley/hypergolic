type Listener = () => void;

const DEBOUNCE_MS = 1000;

const listeners = new Set<Listener>();
let es: EventSource | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let disposed = false;
let currentSessionId: string | null = null;

function fireListeners() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    listeners.forEach((fn) => fn());
  }, DEBOUNCE_MS);
}

function disconnect() {
  es?.close();
  es = null;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (debounceTimer) {
    clearTimeout(debounceTimer);
    debounceTimer = null;
  }
}

function connect() {
  if (disposed || es) return;
  // Without a sessionId there's nothing to scope the watch to; just sit
  // idle until setWatchScope gives us one. The SSE endpoint requires
  // session_id and would 422 otherwise.
  if (!currentSessionId) return;
  const base = `${window.location.protocol}//${window.location.host}/api/files/watch`;
  const url = `${base}?session_id=${encodeURIComponent(currentSessionId)}`;
  es = new EventSource(url);

  es.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "changes") {
      fireListeners();
    }
  };

  es.onerror = () => {
    es?.close();
    es = null;
    if (!disposed && listeners.size > 0) {
      reconnectTimer = setTimeout(connect, 3000);
    }
  };
}

function ensureConnection() {
  if (!es && listeners.size > 0) {
    disposed = false;
    connect();
  }
}

function maybeDisconnect() {
  if (listeners.size === 0) {
    disposed = true;
    disconnect();
  }
}

export function setWatchScope(scope: { sessionId: string | null }): void {
  if (scope.sessionId === currentSessionId) return;
  currentSessionId = scope.sessionId;
  if (es) {
    disconnect();
    if (listeners.size > 0 && currentSessionId) {
      disposed = false;
      connect();
    }
  } else if (listeners.size > 0 && currentSessionId) {
    // We had listeners but no session to scope to — now we do.
    disposed = false;
    connect();
  }
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  ensureConnection();
  return () => {
    listeners.delete(fn);
    maybeDisconnect();
  };
}
