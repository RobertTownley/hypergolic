import { Component, type ReactNode, type ErrorInfo } from "react";
import styles from "./ErrorBoundary.module.css";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null, errorInfo: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    this.setState({ errorInfo });
    console.error("[ErrorBoundary]", error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleCopy = () => {
    const { error, errorInfo } = this.state;
    const text = [error?.toString(), errorInfo?.componentStack].filter(Boolean).join("\n\n");
    navigator.clipboard.writeText(text);
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    const { error, errorInfo } = this.state;

    return (
      <div className={styles.container}>
        <span className={styles.icon}>⚠️</span>
        <h2 className={styles.title}>Something went wrong</h2>
        <p className={styles.description}>
          The UI encountered an unexpected error. You can reload or copy the details below for
          debugging.
        </p>
        <div className={styles.actions}>
          <button className={styles.primaryButton} onClick={this.handleReload}>
            🔄 Reload
          </button>
          <button className={styles.secondaryButton} onClick={this.handleCopy}>
            📋 Copy Error
          </button>
        </div>
        <pre className={styles.errorDetails}>
          {error?.toString()}
          {errorInfo?.componentStack && (
            <>
              {"\n\nComponent Stack:"}
              {errorInfo.componentStack}
            </>
          )}
        </pre>
      </div>
    );
  }
}

