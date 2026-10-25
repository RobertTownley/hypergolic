import { Text } from "@/shared/components/Text";
import { FileIcon, FolderOpenIcon } from "lucide-react";
import type { FileNode } from "@/types/api";
import styles from "./FileViewer.module.css";

export function DirectoryView({ path, entries }: { path: string; entries: FileNode[] | null }) {
  const dirName = path.split("/").pop() ?? path;
  const nodes = entries ?? [];
  const dirs = nodes.filter((n) => n.is_dir);
  const files = nodes.filter((n) => !n.is_dir);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <FolderOpenIcon className={styles.headerIcon} />
        <Text className={styles.headerPath} ellipsis title={path}>
          {path}
        </Text>
        <Text className={styles.headerFilename}>{dirName}</Text>
      </div>
      <div className={styles.directoryListing}>
        {nodes.length === 0 ? (
          <span className={styles.directoryEmpty}>Empty directory</span>
        ) : (
          [...dirs, ...files].map((node) => (
            <div key={node.path} className={styles.directoryEntry}>
              {node.is_dir
                ? <FolderOpenIcon className={styles.dirEntryIcon} />
                : <FileIcon className={styles.fileEntryIcon} />}
              <Text className={styles.dirEntryName}>{node.name}</Text>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
