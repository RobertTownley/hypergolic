import { Text } from "@/shared/components/Text";
import { FileIcon } from "lucide-react";
import styles from "./FileViewer.module.css";

export function FileHeader({ path }: { path: string }) {
  const filename = path.split("/").pop() ?? path;
  return (
    <div className={styles.header}>
      <FileIcon className={styles.headerIcon} />
      <Text className={styles.headerPath} ellipsis title={path}>
        {path}
      </Text>
      <Text className={styles.headerFilename}>
        {filename}
      </Text>
    </div>
  );
}
