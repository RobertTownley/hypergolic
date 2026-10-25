export interface SandboxRoot {
  id: string;
  label: string;
  path: string;
}

export interface SandboxContainer {
  id: string;
  roots: SandboxRoot[];
}

export interface SandboxContainersResponse {
  session_id: string;
  containers: SandboxContainer[];
}

export interface SandboxNode {
  name: string;
  path: string;
  is_dir: boolean;
}

export interface SandboxTreeResponse {
  container: string;
  root: string;
  path: string;
  nodes: SandboxNode[];
}

export interface SandboxContentResponse {
  container: string;
  path: string;
  content: string;
  language: string;
  truncated: boolean;
}
