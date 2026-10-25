import type { AppDispatch } from "@/store";
import {
  addAssistantMessage,
  addToolResult,
  appendToolOutput,
  startContentBlock,
  appendContentDelta,
  clearStreamingContent,
  loadMessages,
  setPendingApproval,
} from "@/store/messagesSlice";
import { updateSessionWorkflow, updateSessionDescription, setConcludeError } from "@/store/sessionsSlice";
import {
  handleDone, handleInterrupted, handleError, handleDispatchStarted, handleSessionConcluded,
  handleSessionStatusChange, handleSandboxStatusChange,
} from "./wsEventHandlers";
import type { WsEvent } from "@/types/api";

export function handleWsEvent(dispatch: AppDispatch, event: WsEvent): void {
  switch (event.type) {
    case "content_block_start": {
      const b = event.content[0];
      dispatch(startContentBlock({
        sessionId: event.session_id, index: b.index, blockType: b.type,
        id: b.id, name: b.name, display_name: b.display_name, startedAt: Date.now(),
      }));
      break;
    }
    case "content_block_delta": {
      const d = event.content[0];
      dispatch(appendContentDelta({
        sessionId: event.session_id, index: d.index, text: d.text, thinking: d.thinking, partialJson: d.partial_json,
      }));
      break;
    }
    case "content_block_stop":
      break;
    case "assistant_message":
      dispatch(clearStreamingContent(event.session_id));
      dispatch(addAssistantMessage({
        sessionId: event.session_id, content: event.content, model: event.model,
        stopReason: event.stop_reason, messageId: event.message_id, usage: event.usage,
      }));
      break;
    case "tool_result":
      dispatch(addToolResult({ sessionId: event.session_id, content: event.content }));
      break;
    case "tool_output_chunk":
      for (const chunk of event.content) {
        dispatch(appendToolOutput({ toolUseId: chunk.tool_use_id, text: chunk.text }));
      }
      break;
    case "done":
      handleDone(dispatch, event);
      break;
    case "interrupted":
      handleInterrupted(dispatch, event);
      break;
    case "error":
      handleError(dispatch, event);
      break;
    case "tool_approval_request":
      dispatch(setPendingApproval({
        toolUseId: event.tool_use_id,
        toolName: event.tool_display_name ?? event.tool_name,
        toolId: event.tool_name,
        approvalView: event.approval_view,
        toolInput: event.tool_input,
        sessionId: event.session_id,
      }));
      break;
    case "sandbox_status_change":
      handleSandboxStatusChange(dispatch, event);
      break;
    case "session_status_change":
      handleSessionStatusChange(dispatch, event);
      break;
    case "truncated":
      dispatch(loadMessages(event.session_id));
      break;
    case "workflow_state_change": {
      const c = event.content[0];
      dispatch(updateSessionWorkflow({
        sessionId: event.session_id, workflowId: c.workflow_id, workflowName: c.workflow_name,
        workflowStateId: c.workflow_state_id, workflowStateName: c.workflow_state_name,
      }));
      break;
    }
    case "dispatch_started":
      handleDispatchStarted(dispatch, event);
      break;
    case "dispatch_concluded":
      break;
    case "session_description_update": {
      const desc = event.content[0];
      dispatch(updateSessionDescription({ sessionId: event.session_id, description: desc.description }));
      break;
    }
    case "session_concluded":
      handleSessionConcluded(dispatch, event);
      break;
    case "conclude_error":
      // Store-backed so the error survives the session's ChatView being
      // unmounted: useConcludeModals re-opens the modal from this record
      // when the user is (or returns to) the session.
      dispatch(setConcludeError({ sessionId: event.session_id, detail: event.detail }));
      break;
  }
}
