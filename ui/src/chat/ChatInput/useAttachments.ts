import { useState, useCallback, useMemo } from "react";
import type { Attachment, FileAttachment } from "@/types/api";
import { useAppSelector, useAppDispatch } from "@/store";
import { uploadAttachment } from "@/api/sessions";
import {
  selectDraft,
  setDraftFileAttachments,
  removeDraftCodeSelection,
  removeDraftSummaryRecall,
} from "@/store/uiSlice";

let attachmentIdCounter = 0;

function acceptedFiles(files: FileList): File[] {
  return Array.from(files).filter(
    (f) => f.type.startsWith("image/") || f.type === "application/pdf",
  );
}

async function toFileAttachment(file: File): Promise<FileAttachment> {
  const block = await uploadAttachment(file);
  const source = block.source!;
  const id = `attachment-${++attachmentIdCounter}`;
  if (block.type === "document") {
    return { id, type: "document", source, filename: file.name };
  }
  const preview = `data:${source.media_type};base64,${source.data}`;
  return { id, type: "image", source, preview, filename: file.name };
}

export function useAttachments(sessionId: string, onUploaded: () => void) {
  const dispatch = useAppDispatch();
  const { fileAttachments, codeSelections, summaryRecalls } = useAppSelector((s) => selectDraft(s, sessionId));
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);

  const allAttachments: Attachment[] = useMemo(
    () => [...summaryRecalls, ...codeSelections, ...fileAttachments],
    [summaryRecalls, codeSelections, fileAttachments],
  );

  const processFiles = useCallback(async (accepted: File[]) => {
    if (accepted.length === 0) return;

    setUploading(true);
    try {
      const results = await Promise.all(accepted.map(toFileAttachment));
      dispatch(setDraftFileAttachments({ sessionId, attachments: [...fileAttachments, ...results] }));
      onUploaded();
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploading(false);
    }
  }, [sessionId, fileAttachments, dispatch, onUploaded]);

  const removeAttachment = useCallback((id: string) => {
    if (summaryRecalls.some((a) => a.id === id)) {
      dispatch(removeDraftSummaryRecall({ sessionId, id }));
    } else if (codeSelections.some((a) => a.id === id)) {
      dispatch(removeDraftCodeSelection({ sessionId, id }));
    } else {
      dispatch(setDraftFileAttachments({
        sessionId,
        attachments: fileAttachments.filter((a) => a.id !== id),
      }));
    }
  }, [sessionId, summaryRecalls, codeSelections, fileAttachments, dispatch]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      processFiles(acceptedFiles(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(acceptedFiles(e.target.files));
      e.target.value = "";
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const files = acceptedFiles(e.clipboardData.files);
    if (files.length === 0) return;
    e.preventDefault();
    processFiles(files);
  };

  return {
    allAttachments,
    uploading,
    dragOver,
    previewAttachment,
    setPreviewAttachment,
    removeAttachment,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleFileSelect,
    handlePaste,
  };
}
