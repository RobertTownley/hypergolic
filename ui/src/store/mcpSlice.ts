import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import type { MCPServerInfo } from "@/types/api";
import * as api from "@/api/mcp";
import { getProjectId } from "@/store/selectors";
import { loadSessionContext } from "@/store/sessionsSlice";
import type { RootState, AppDispatch } from "@/store";

interface MCPState {
  servers: MCPServerInfo[];
  enabledBySessionId: Record<string, string[]>;
  loading: boolean;
  connecting: Record<string, boolean>;
}

const initialState: MCPState = {
  servers: [],
  enabledBySessionId: {},
  loading: false,
  connecting: {},
};

export const loadMCPServers = createAsyncThunk("mcp/loadServers", async (_, { getState }) => {
  const projectId = getProjectId(getState() as RootState);
  return api.fetchMCPServers(projectId);
});

export const loadSessionEnabledServers = createAsyncThunk(
  "mcp/loadSessionEnabled",
  async (sessionId: string) => {
    const enabled = await api.fetchSessionEnabledServers(sessionId);
    return { sessionId, enabled };
  }
);

export const toggleMCPServer = createAsyncThunk(
  "mcp/toggle",
  async ({ serverName, sessionId, enable }: { serverName: string; sessionId: string; enable: boolean }, { getState, dispatch }) => {
    const projectId = getProjectId(getState() as RootState);
    if (enable) {
      const info = await api.connectMCPServer(serverName, sessionId, projectId);
      const enabled = await api.fetchSessionEnabledServers(sessionId);
      const servers = await api.fetchMCPServers(projectId);
      (dispatch as AppDispatch)(loadSessionContext(sessionId));
      return { info, sessionId, enabled, servers };
    } else {
      const info = await api.disconnectMCPServer(serverName, sessionId, projectId);
      const enabled = await api.fetchSessionEnabledServers(sessionId);
      const servers = await api.fetchMCPServers(projectId);
      (dispatch as AppDispatch)(loadSessionContext(sessionId));
      return { info, sessionId, enabled, servers };
    }
  }
);

const mcpSlice = createSlice({
  name: "mcp",
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(loadMCPServers.pending, (state) => {
        state.loading = true;
      })
      .addCase(loadMCPServers.fulfilled, (state, action) => {
        state.loading = false;
        state.servers = action.payload;
      })
      .addCase(loadMCPServers.rejected, (state) => {
        state.loading = false;
      })
      .addCase(loadSessionEnabledServers.fulfilled, (state, action) => {
        const { sessionId, enabled } = action.payload;
        state.enabledBySessionId[sessionId] = enabled;
      })
      .addCase(toggleMCPServer.pending, (state, action) => {
        state.connecting[action.meta.arg.serverName] = true;
      })
      .addCase(toggleMCPServer.fulfilled, (state, action) => {
        const { sessionId, enabled, servers } = action.payload;
        state.enabledBySessionId[sessionId] = enabled;
        state.servers = servers;
        state.connecting[action.meta.arg.serverName] = false;
      })
      .addCase(toggleMCPServer.rejected, (state, action) => {
        state.connecting[action.meta.arg.serverName] = false;
      });
  },
});

export default mcpSlice.reducer;
