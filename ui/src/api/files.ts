import type {
  FileTreeResponse,
  FileContentResponse,
  SandboxContainersResponse,
  SandboxTreeResponse,
  SandboxContentResponse,
} from "@/types/api";
import type { SessionScope } from "@/api/git";
import { errorDetail, getJson, request } from "@/api/http";

const BASE = "/api";

function scopeQuery(scope: SessionScope): string {
  return `?session_id=${encodeURIComponent(scope.sessionId)}`;
}

export async function fetchFileTree(scope: SessionScope): Promise<FileTreeResponse> {
  return getJson(`${BASE}/files/tree${scopeQuery(scope)}`, "Failed to fetch file tree");
}

export async function fetchFileContent(path: string, scope: SessionScope): Promise<FileContentResponse> {
  return getJson(`${BASE}/files/read${scopeQuery(scope)}&path=${encodeURIComponent(path)}`, "Failed to read file");
}

export async function fetchHarnessFileTree(): Promise<FileTreeResponse> {
  return getJson("/api/harness/files/tree", "Failed to fetch harness file tree");
}

export async function fetchHarnessFileContent(path: string): Promise<FileContentResponse> {
  return getJson(`/api/harness/files/read?path=${encodeURIComponent(path)}`, "Failed to read harness file");
}

type SaveFilePicker = (options: {
  suggestedName?: string;
  types?: { description?: string; accept: Record<string, string[]> }[];
}) => Promise<{ createWritable: () => Promise<{ write: (b: Blob) => Promise<void>; close: () => Promise<void> }> }>;

export async function downloadHarnessConfig(): Promise<void> {
  const res = await request("/api/harness/files/export", "Failed to export harness config");
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? "hypergolic-config.zip";

  const picker = (window as { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker;
  if (picker) {
    let handle: Awaited<ReturnType<SaveFilePicker>> | undefined;
    try {
      handle = await picker({
        suggestedName: filename,
        types: [{ description: "ZIP archive", accept: { "application/zip": [".zip"] } }],
      });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      handle = undefined;
    }
    if (handle) {
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    }
  }

  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function fetchSandboxContainers(
  scope: SessionScope,
): Promise<SandboxContainersResponse> {
  return getJson(`${BASE}/files/sandbox/containers${scopeQuery(scope)}`, "Failed to fetch sandbox containers");
}

export async function fetchSandboxTree(
  container: string,
  root: string,
  path: string | null,
  scope: SessionScope,
): Promise<SandboxTreeResponse> {
  const params = new URLSearchParams({
    session_id: scope.sessionId,
    container,
    root,
  });
  if (path) params.set("path", path);
  return getJson(`${BASE}/files/sandbox/tree?${params.toString()}`, (r) => sandboxError(r, "list sandbox directory"));
}

export async function fetchSandboxContent(
  container: string,
  root: string,
  path: string,
  scope: SessionScope,
): Promise<SandboxContentResponse> {
  const params = new URLSearchParams({
    session_id: scope.sessionId,
    container,
    root,
    path,
  });
  return getJson(`${BASE}/files/sandbox/read?${params.toString()}`, (r) => sandboxError(r, "read sandbox file"));
}

// The server answers 503 while the container is still coming up. Naming the
// error lets reducers render "starting" (and retry) instead of a red failure.
export const SANDBOX_STARTING = "SandboxStarting";

async function sandboxError(res: Response, action: string): Promise<Error> {
  const error = new Error(await errorDetail(res, `Failed to ${action}`));
  if (res.status === 503) error.name = SANDBOX_STARTING;
  return error;
}
