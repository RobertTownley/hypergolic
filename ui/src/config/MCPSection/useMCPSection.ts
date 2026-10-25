import { useEffect, useState } from "react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectActiveProjectId } from "@/store/selectors";
import { loadMCPServers, loadSessionEnabledServers, toggleMCPServer } from "@/store/mcpSlice";

export function useMCPSection() {
  const dispatch = useAppDispatch();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const activeProjectId = useAppSelector(selectActiveProjectId);
  const servers = useAppSelector((s) => s.mcp.servers);
  const enabledMap = useAppSelector((s) => s.mcp.enabledBySessionId);
  const connecting = useAppSelector((s) => s.mcp.connecting);
  const streaming = useAppSelector((s) =>
    activeSessionId ? !!s.messages.streamingSessions[activeSessionId] : false,
  );
  const [expanded, setExpanded] = useState(false);

  const contextMcpEnabled = useAppSelector(
    (s) => activeSessionId ? s.sessions.contextBySessionId[activeSessionId]?.mcp_enabled : undefined,
  );
  const enabled = activeSessionId
    ? (enabledMap[activeSessionId] ?? contextMcpEnabled ?? [])
    : [];

  useEffect(() => {
    dispatch(loadMCPServers());
  }, [dispatch, activeProjectId]);

  useEffect(() => {
    if (expanded && activeSessionId) {
      dispatch(loadSessionEnabledServers(activeSessionId));
    }
  }, [expanded, activeSessionId, dispatch]);

  const handleToggle = (serverName: string, currentlyEnabled: boolean) => {
    if (!activeSessionId || streaming) return;
    dispatch(toggleMCPServer({
      serverName,
      sessionId: activeSessionId,
      enable: !currentlyEnabled,
    }));
  };

  return {
    servers,
    enabled,
    connecting,
    streaming,
    activeSessionId,
    expanded,
    setExpanded,
    handleToggle,
  };
}
