import { ArrowUpIcon, GitBranchIcon, PaperclipIcon, XIcon } from "lucide-react";
import type { ContentBlock, ModelTier } from "@/types/api";
import { ImageModal } from "@/modals/ImageModal";
import { CodeSelectionModal } from "@/modals/CodeSelectionModal";
import { SlashMenu } from "./SlashMenu";
import { AttachmentBar } from "./AttachmentBar";
import { useChatInput } from "./useChatInput";
import styles from "./ChatInput.module.css";

interface ChatInputProps {
  sessionId: string;
  onSend: (message: string, modelTier: ModelTier, contentBlocks?: ContentBlock[], workflowId?: string) => void;
  streaming: boolean;
}

export function ChatInput({ sessionId, onSend, streaming }: ChatInputProps) {
  const {
    text,
    selectedWorkflow,
    menu,
    allAttachments,
    uploading,
    dragOver,
    previewAttachment,
    textareaRef,
    fileInputRef,
    setPreviewAttachment,
    removeAttachment,
    handleSend,
    handleKeyDown,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelect,
    handlePaste,
    handleTextChange,
    clearWorkflow,
    openFilePicker,
  } = useChatInput({ sessionId, onSend });

  return (
    <div
      className={`${styles.container} ${dragOver ? styles.dragOver : ""}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <AttachmentBar
        attachments={allAttachments}
        uploading={uploading}
        onPreview={setPreviewAttachment}
        onRemove={removeAttachment}
      />
      <div className={styles.inputWrapper}>
        {menu.open && (
          <SlashMenu
            commands={menu.items}
            selectedIndex={menu.selectedIndex}
            onSelect={menu.select}
            onHover={menu.setIndex}
          />
        )}
        {selectedWorkflow && (
          <span className={styles.workflowPill}>
            <GitBranchIcon />
            {selectedWorkflow.name}
            <button className={styles.workflowClear} onClick={clearWorkflow} aria-label="Clear workflow">
              <XIcon />
            </button>
          </span>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,application/pdf"
          onChange={handleFileSelect}
          style={{ display: "none" }}
        />
        <textarea
          ref={textareaRef}
          className={styles.textarea}
          rows={1}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder={dragOver ? "Drop images or PDFs here..." : streaming ? "Send a message to interrupt..." : "Send a message..."}
        />
        <div className={styles.actions}>
          <button
            type="button"
            aria-label="Attach files"
            onClick={openFilePicker}
            disabled={streaming}
            className={styles.attachButton}
          >
            <PaperclipIcon />
          </button>
          <button
            type="button"
            aria-label={streaming ? "Interrupt" : "Send"}
            onClick={handleSend}
            disabled={!text.trim() && allAttachments.length === 0}
            className={`${styles.sendButton} ${streaming ? styles.interruptButton : ""}`}
          >
            <ArrowUpIcon />
          </button>
        </div>
      </div>

      {previewAttachment?.type === "image" && (
        <ImageModal
          src={previewAttachment.preview}
          alt={previewAttachment.filename}
          onClose={() => setPreviewAttachment(null)}
        />
      )}
      {previewAttachment?.type === "code_selection" && (
        <CodeSelectionModal
          selection={previewAttachment.selection}
          onClose={() => setPreviewAttachment(null)}
        />
      )}
    </div>
  );
}
