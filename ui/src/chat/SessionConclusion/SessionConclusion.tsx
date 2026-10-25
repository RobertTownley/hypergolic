import { ClockIcon, MessageSquareIcon, StarIcon } from "lucide-react";
import styles from "./SessionConclusion.module.css";

interface SessionConclusionProps {
  conclusionRating: number | null;
  conclusionFeedback: string | null;
  concludedAt: string | null;
  concluding?: boolean;
}

function RatingStars({ rating }: { rating: number }) {
  return (
    <span className={styles.stars} data-testid="rating-stars">
      {[1, 2, 3, 4, 5].map((i) =>
        i <= rating ? (
          <StarIcon key={i} className={styles.starFilled} fill="currentColor" />
        ) : (
          <StarIcon key={i} className={styles.starEmpty} />
        ),
      )}
    </span>
  );
}

function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function SessionConclusion({
  conclusionRating,
  conclusionFeedback,
  concludedAt,
  concluding,
}: SessionConclusionProps) {
  return (
    <div className={styles.container} data-testid="session-conclusion">
      <div className={styles.header}>
        <span className={styles.title}>{concluding ? "Concluding \u2014 distilling learnings\u2026" : "Session Concluded"}</span>
        {conclusionRating !== null && <RatingStars rating={conclusionRating} />}
      </div>

      {concludedAt && (
        <div className={styles.meta}>
          <ClockIcon />
          <span>{formatTimestamp(concludedAt)}</span>
        </div>
      )}

      {conclusionFeedback && (
        <div className={styles.feedbackSection}>
          <div className={styles.sectionLabel}>
            <MessageSquareIcon /> Feedback
          </div>
          <div className={styles.feedbackText} data-testid="conclusion-feedback">{conclusionFeedback}</div>
        </div>
      )}
    </div>
  );
}
