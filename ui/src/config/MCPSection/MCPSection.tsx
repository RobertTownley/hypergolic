import { Tooltip } from "@/shared/components/Tooltip";
import { LoaderCircleIcon, PlugIcon } from "lucide-react";
import { Badge } from "@/shared/components/Badge";
import { Collapsible } from "@/shared/components/Collapsible";
import { useMCPSection } from "./useMCPSection";
import type { MCPServerInfo } from "@/types/api";
import styles from "./MCPSection.module.css";

function getStatusDotClass(server: MCPServerInfo, isEnabled: boolean): string {
  if (isEnabled) return `${styles.statusDot} ${styles.statusEnabled}`;
  if (server.auth_status === "needs_oauth" || server.auth_status === "missing_token") {
    return `${styles.statusDot} ${styles.statusNeedsAuth}`;
  }
  return styles.statusDot;
}

function getTooltipText(server: MCPServerInfo): string {
  const parts = [`Source: ${server.source}`, `Transport: ${server.transport}`];
  if (server.connected) parts.push(`${server.tool_count} tools`);
  if (server.auth_type === "oauth") {
    if (server.auth_status === "needs_oauth") parts.push("OAuth required \u2014 enable to authorize");
    else if (server.auth_status === "ready") parts.push("OAuth: authorized");
  } else if (server.auth_type === "token") {
    if (server.auth_status === "missing_token") parts.push("API token env var not set");
    else if (server.auth_status === "ready") parts.push("Token: configured");
  }
  return parts.join(" \u00b7 ");
}

export function MCPSection() {
  const { servers, enabled, connecting, streaming, activeSessionId, expanded, setExpanded, handleToggle } = useMCPSection();

  if (servers.length === 0) return null;

  return (
    <Collapsible
      icon={<PlugIcon />}
      title={`MCP (${enabled.length}/${servers.length})`}
      expanded={expanded}
      onToggle={setExpanded}
      bodyClassName={styles.serverList}
    >
      {servers.map((server: MCPServerInfo) => {
        const isEnabled = enabled.includes(server.name);
        const isConnecting = connecting[server.name] ?? false;
        const isDisabled = !activeSessionId || streaming || server.auth_status === "missing_token";

        return (
          <div key={server.name} className={styles.serverRow}>
            <label className={styles.checkboxLabel}>
              {isConnecting ? (
                <LoaderCircleIcon className={`icon-spin ${styles.spinner}`} />
              ) : (
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={() => handleToggle(server.name, isEnabled)}
                  disabled={isDisabled}
                  className={styles.checkbox}
                />
              )}
              <span className={styles.serverName}>{server.name}</span>
              {server.auth_status === "needs_oauth" && !isEnabled && <Badge variant="warning">OAuth</Badge>}
              {server.auth_status === "missing_token" && <Badge variant="warning">No token</Badge>}
            </label>
            <Tooltip title={getTooltipText(server)}>
              <span className={getStatusDotClass(server, isEnabled)} />
            </Tooltip>
          </div>
        );
      })}
    </Collapsible>
  );
}
