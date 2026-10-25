import { ChevronDownIcon, ChevronRightIcon } from "lucide-react";
import type { ToolInfo } from "@/types/api";
import { Badge } from "@/shared/components/Badge";
import { ToolParams } from "./ToolParams";
import { mcpDisplayName } from "./constants";
import styles from "./ToolsModal.module.css";

export function ToolRow({ tool, expanded, onToggle }: {
  tool: ToolInfo;
  expanded: boolean;
  onToggle: () => void;
}) {
  const displayName = tool.reason.startsWith("mcp:") ? mcpDisplayName(tool.name) : tool.name;
  const hasParams = tool.input_schema && Object.keys(tool.input_schema.properties as object ?? {}).length > 0;
  const tokens = tool.token_estimate >= 1_000
    ? `${(tool.token_estimate / 1_000).toFixed(1)}k`
    : `${tool.token_estimate}`;

  return (
    <div className={styles.toolRow}>
      <div className={styles.toolLine} onClick={onToggle}>
        <span className={styles.expandIcon}>
          {expanded ? <ChevronDownIcon /> : <ChevronRightIcon />}
        </span>
        <span className={styles.toolName}>
          {displayName}
          {tool.id !== displayName && <span className={styles.toolId}>(id: {tool.id})</span>}
          <span className={styles.toolTokens}>
            {tool.token_estimate === 0 ? "no wire cost" : `~${tokens} tok`}
          </span>
        </span>
        <span className={styles.toolMeta}>
          {tool.requires_approval && (
            <Badge variant="error" uppercase>approval</Badge>
          )}
        </span>
      </div>
      {expanded && (
        <div className={styles.toolDetail}>
          {tool.usage && <code className={styles.toolUsage}>{tool.usage}</code>}
          <p className={styles.toolDesc}>{tool.description}</p>
          {hasParams && <ToolParams schema={tool.input_schema as Record<string, unknown>} />}
        </div>
      )}
    </div>
  );
}
