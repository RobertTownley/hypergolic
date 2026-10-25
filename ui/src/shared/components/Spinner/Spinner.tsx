import styles from "./Spinner.module.css";

type SpinnerSize = "small" | "default" | "large";

interface SpinnerProps {
  size?: SpinnerSize;
  className?: string;
  centered?: boolean;
}

function Dots({ size, className }: { size: SpinnerSize; className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`${styles.spinner} ${styles[size]} ${className ?? ""}`}
    >
      <i /><i /><i /><i />
    </span>
  );
}

export function Spinner({ size = "default", className, centered = false }: SpinnerProps) {
  if (centered) {
    return (
      <div className={`${styles.centered} ${className ?? ""}`}>
        <Dots size={size} />
      </div>
    );
  }
  return <Dots size={size} className={className} />;
}
