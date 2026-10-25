import { useMemo } from "react";
import { useAppSelector } from "@/store";
import { commentsToAnnotations, type ReviewComment } from "@/store/reviewSlice";
import type { Annotation } from "@/types/api";

const EMPTY_COMMENTS: ReviewComment[] = [];

export interface ReviewDenial {
  annotations: Annotation[] | undefined;
  reason: (typed?: string) => string | undefined;
}

export function useReviewDenial(sessionId: string): ReviewDenial {
  const comments = useAppSelector(
    (s) => s.review.bySession[sessionId]?.comments ?? EMPTY_COMMENTS,
  );
  const overallNote = useAppSelector(
    (s) => s.review.bySession[sessionId]?.overallNote ?? "",
  );
  return useMemo(() => {
    const annotations = commentsToAnnotations(comments);
    return {
      annotations,
      reason: (typed?: string) =>
        [typed?.trim(), overallNote.trim()].filter(Boolean).join("\n\n") ||
        (annotations ? "See inline review comments." : undefined),
    };
  }, [comments, overallNote]);
}
