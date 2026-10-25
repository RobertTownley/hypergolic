import { SearchIcon } from "lucide-react";
import { EmptyState } from "@/shared/components/EmptyState";
import { TogglePill } from "./TogglePill";
import { ResultItem } from "./ResultItem";
import { SessionResultItem } from "./SessionResultItem";
import { PreviewPane } from "./PreviewPane";
import { SessionPreviewPane } from "./SessionPreviewPane";
import { useFileFinder } from "./useFileFinder";
import styles from "./FileFinder.module.css";

export { FILE_FINDER_OPEN_EVENT } from "./types";

const MODE_LABELS = { files: "filenames", contents: "content", all: "all", sessions: "sessions" } as const;

export function FileFinder() {
  const {
    open, query, setQuery, mode, setMode,
    respectGitignore, setRespectGitignore,
    includeHidden, setIncludeHidden,
    results, selectedIndex, setSelectedIndex, loading,
    filePreview, filePreviewLoading, filePreviewError,
    sessionMessages, sessionPreviewLoading, sessionPreviewLabel,
    selectedResult, close, openResult, handleKeyDown,
    inputRef, resultsRef,
  } = useFileFinder();

  if (!open) return null;

  const showFilePreview = selectedResult?.type === "file";
  const showSessionPreview = selectedResult?.type === "session";
  const highlightLine = showFilePreview && selectedResult.match.line ? selectedResult.match.line : null;

  return (
    <div className={styles.overlay} onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className={styles.container} onKeyDown={handleKeyDown}>
        <div className={styles.inputRow}>
          <SearchIcon className={styles.searchIcon} />
          <input
            ref={inputRef}
            className={styles.input}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${MODE_LABELS[mode]}\u2026`}
            spellCheck={false}
            autoComplete="off"
          />
        </div>

        <div className={styles.toggleBar}>
          <TogglePill label="All" shortcut={"\u2318A"} active={mode === "all"} onClick={() => setMode("all")} />
          <TogglePill label="Content" shortcut={"\u2318C"} active={mode === "contents"} onClick={() => setMode("contents")} />
          <TogglePill label="Filenames" shortcut={"\u2318F"} active={mode === "files"} onClick={() => setMode("files")} />
          <TogglePill label="Sessions" shortcut={"\u2318S"} active={mode === "sessions"} onClick={() => setMode("sessions")} />
          <span style={{ flex: 1 }} />
          {mode !== "sessions" && (
            <>
              <TogglePill label=".gitignore" shortcut={"\u2318G"} active={respectGitignore} onClick={() => setRespectGitignore((v) => !v)} />
              <TogglePill label="Hidden" shortcut={"\u2318H"} active={includeHidden} onClick={() => setIncludeHidden((v) => !v)} />
            </>
          )}
        </div>

        <div className={styles.body}>
          <div className={styles.listPane}>
            <div className={styles.results} ref={resultsRef}>
              {results.length === 0 && query.trim() && !loading && <EmptyState text="No results found" />}
              {results.length === 0 && !query.trim() && <EmptyState text={"Type to search\u2026"} />}
              {results.map((result, i) =>
                result.type === "file" ? (
                  <ResultItem
                    key={`file:${result.match.path}:${result.match.line ?? 0}:${i}`}
                    match={result.match}
                    selected={i === selectedIndex}
                    onClick={() => openResult(result)}
                    onMouseEnter={() => setSelectedIndex(i)}
                  />
                ) : (
                  <SessionResultItem
                    key={`session:${result.match.session_id}:${i}`}
                    match={result.match}
                    selected={i === selectedIndex}
                    onClick={() => openResult(result)}
                    onMouseEnter={() => setSelectedIndex(i)}
                  />
                ),
              )}
            </div>
          </div>
          {showFilePreview && (
            <PreviewPane preview={filePreview} loading={filePreviewLoading} error={filePreviewError} highlightLine={highlightLine} />
          )}
          {showSessionPreview && (
            <SessionPreviewPane messages={sessionMessages} loading={sessionPreviewLoading} label={sessionPreviewLabel} />
          )}
          {!selectedResult && (
            <PreviewPane preview={null} loading={false} error={null} highlightLine={null} />
          )}
        </div>

        <div className={styles.footer}>
          <span className={styles.footerHint}><span className={styles.kbd}>{"\u2191\u2193"}</span> navigate</span>
          <span className={styles.footerHint}><span className={styles.kbd}>{"\u21B5"}</span> open</span>
          <span className={styles.footerHint}><span className={styles.kbd}>esc</span> close</span>
        </div>
      </div>
    </div>
  );
}
