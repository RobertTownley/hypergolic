export interface RoleInfo {
  id: string;
  name: string;
  source: string;
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  source: string;
}

export interface PromptPartInfo {
  source: string;
  content: string;
  token_estimate: number;
}

interface WorkflowToolInfo {
  id: string;
  name: string;
  description: string;
}

interface WorkflowOutputSchemaInfo {
  outcome: string;
  next_state: string | null;
  artifact_id: string | null;
  requires_approval: boolean;
  display: Record<string, string> | null;
  schema_def: Record<string, unknown>;
}

interface WorkflowSkillInfo {
  id: string;
  name: string;
}

interface WorkflowStateInfo {
  id: string;
  name: string;
  prompt_path: string | null;
  skills: WorkflowSkillInfo[];
  tools: WorkflowToolInfo[];
  truncate_on_entry: boolean;
  include_artifacts: string[];
  output_schemas: WorkflowOutputSchemaInfo[];
}

export interface WorkflowInfo {
  id: string;
  name: string;
  description: string;
  prompt_path: string | null;
  initial_state: string;
  states: WorkflowStateInfo[];
}
