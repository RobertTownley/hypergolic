import { Tree } from "@/shared/components/Tree";
import { FolderIcon, RotateCwIcon } from "lucide-react";
import { useAppDispatch, useAppSelector } from "@/store";
import { selectFileSource } from "@/store/selectors";
import { setFileSource } from "@/store/workspaceSlice";
import { type FileSource } from "@/store/workspace/state";
import { useFileExplorer } from "./useFileExplorer";
import { useSandboxExplorer } from "./useSandboxExplorer";
import { SourceToggle } from "./SourceToggle";
import { SandboxControls } from "./SandboxControls";
import { Panel, PanelHeader, PanelBody } from "@/shared/components/Panel";
import { Spinner } from "@/shared/components/Spinner";
import { IconButton } from "@/shared/components/IconButton";
import styles from "./FileExplorer.module.css";

export function FileExplorer() {
  const dispatch = useAppDispatch();
  const source = useAppSelector(selectFileSource);

  return (
    <Panel>
      <SourceToggle value={source} onChange={(s: FileSource) => dispatch(setFileSource(s))} />
      {source === "host" ? <HostView /> : <SandboxView />}
    </Panel>
  );
}

function HostView() {
  const {
    loading,
    tree,
    treeData,
    rootName,
    selectedFilePath,
    expandedKeys,
    handleSelect,
    handleExpand,
    refresh,
  } = useFileExplorer();

  return (
    <>
      <PanelHeader
        icon={<FolderIcon />}
        actions={<IconButton icon={<RotateCwIcon />} tooltip="Refresh" onClick={refresh} />}
      >
        {rootName}
      </PanelHeader>
      <PanelBody scrollable className={styles.treeContainer}>
        {loading && tree.length === 0 ? (
          <Spinner centered />
        ) : (
          <Tree
            aria-label="Project files"
            treeData={treeData}
            selectedKey={selectedFilePath}
            onSelect={handleSelect}
            expandedKeys={expandedKeys}
            onExpand={handleExpand}
          />
        )}
      </PanelBody>
    </>
  );
}

function SandboxView() {
  const {
    containers,
    containersLoaded,
    container,
    root,
    roots,
    treeData,
    expandedKeys,
    selectedPath,
    loading,
    error,
    starting,
    handleSelectContainer,
    handleSelectRoot,
    handleExpand,
    handleLoadData,
    handleSelect,
    refresh,
  } = useSandboxExplorer();

  const noSandbox = containersLoaded && containers.length === 0;

  return (
    <>
      <PanelHeader
        icon={<FolderIcon />}
        actions={
          <IconButton
            icon={<RotateCwIcon />}
            tooltip="Refresh"
            onClick={refresh}
            disabled={noSandbox}
          />
        }
      >
        {container ?? "Sandbox"}
      </PanelHeader>
      {!noSandbox && (
        <SandboxControls
          containers={containers}
          container={container}
          roots={roots}
          root={root}
          onSelectContainer={handleSelectContainer}
          onSelectRoot={handleSelectRoot}
        />
      )}
      <PanelBody scrollable className={styles.treeContainer}>
        {!containersLoaded ? (
          <Spinner centered />
        ) : noSandbox ? (
          <div className={styles.stateMessage}>
            No sandbox is configured for this session.
          </div>
        ) : starting ? (
          <div className={styles.stateMessage}>Sandbox is starting…</div>
        ) : error ? (
          <div className={`${styles.stateMessage} ${styles.errorMessage}`}>{error}</div>
        ) : loading && treeData.length === 0 ? (
          <Spinner centered />
        ) : treeData.length === 0 ? (
          <div className={styles.stateMessage}>This directory is empty.</div>
        ) : (
          <Tree
            aria-label="Sandbox files"
            treeData={treeData}
            loadData={handleLoadData}
            selectedKey={selectedPath}
            onSelect={handleSelect}
            expandedKeys={expandedKeys}
            onExpand={handleExpand}
          />
        )}
      </PanelBody>
    </>
  );
}
