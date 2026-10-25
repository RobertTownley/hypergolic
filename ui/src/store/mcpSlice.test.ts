import { describe, it, expect } from "vitest";
import mcpReducer, {
  loadMCPServers,
  loadSessionEnabledServers,
  toggleMCPServer,
} from "./mcpSlice";

const initialState = {
  servers: [],
  enabledBySessionId: {} as Record<string, string[]>,
  loading: false,
  connecting: {} as Record<string, boolean>,
};

const sampleServer = {
  name: "my-server",
  source: "user" as const,
  connected: true,
  tool_count: 3,
  transport: "stdio" as const,
  auth_type: "none" as const,
  auth_status: "not_required" as const,
};

describe("mcpSlice", () => {
  it("should return the initial state", () => {
    expect(mcpReducer(undefined, { type: "unknown" })).toEqual(initialState);
  });

  describe("loadMCPServers", () => {
    it("should set loading on pending", () => {
      const action = { type: loadMCPServers.pending.type };
      const state = mcpReducer(initialState, action);
      expect(state.loading).toBe(true);
    });

    it("should store servers on fulfilled", () => {
      const action = { type: loadMCPServers.fulfilled.type, payload: [sampleServer] };
      const state = mcpReducer(initialState, action);
      expect(state.loading).toBe(false);
      expect(state.servers).toEqual([sampleServer]);
    });

    it("should clear loading on rejected", () => {
      const action = { type: loadMCPServers.rejected.type };
      const state = mcpReducer({ ...initialState, loading: true }, action);
      expect(state.loading).toBe(false);
    });
  });

  describe("loadSessionEnabledServers", () => {
    it("should store enabled servers by session id", () => {
      const action = {
        type: loadSessionEnabledServers.fulfilled.type,
        payload: { sessionId: "s1", enabled: ["server-a", "server-b"] },
      };
      const state = mcpReducer(initialState, action);
      expect(state.enabledBySessionId["s1"]).toEqual(["server-a", "server-b"]);
    });
  });

  describe("toggleMCPServer", () => {
    it("should set connecting on pending", () => {
      const action = {
        type: toggleMCPServer.pending.type,
        meta: { arg: { serverName: "my-server", sessionId: "s1", enable: true } },
      };
      const state = mcpReducer(initialState, action);
      expect(state.connecting["my-server"]).toBe(true);
    });

    it("should update state on fulfilled", () => {
      const action = {
        type: toggleMCPServer.fulfilled.type,
        payload: {
          info: sampleServer,
          sessionId: "s1",
          enabled: ["my-server"],
          servers: [sampleServer],
        },
        meta: { arg: { serverName: "my-server", sessionId: "s1", enable: true } },
      };
      const connecting = { ...initialState, connecting: { "my-server": true } };
      const state = mcpReducer(connecting, action);
      expect(state.connecting["my-server"]).toBe(false);
      expect(state.enabledBySessionId["s1"]).toEqual(["my-server"]);
      expect(state.servers).toEqual([sampleServer]);
    });

    it("should clear connecting on rejected", () => {
      const action = {
        type: toggleMCPServer.rejected.type,
        meta: { arg: { serverName: "my-server", sessionId: "s1", enable: true } },
      };
      const connecting = { ...initialState, connecting: { "my-server": true } };
      const state = mcpReducer(connecting, action);
      expect(state.connecting["my-server"]).toBe(false);
    });
  });
});
