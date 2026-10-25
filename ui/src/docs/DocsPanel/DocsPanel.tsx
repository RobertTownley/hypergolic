import { BookIcon, FileTextIcon } from "lucide-react";
import { useDocs } from "@/docs/hooks/useDocs";
import { Panel, PanelHeader, PanelBody } from "@/shared/components/Panel";
import { ListItem, Spinner } from "@/shared/components";
import styles from "./DocsPanel.module.css";

export function DocsPanel() {
  const { entries, entriesLoading, selectedSlug, selectDoc } = useDocs();

  return (
    <Panel>
      <PanelHeader icon={<BookIcon />}>Docs</PanelHeader>
      <PanelBody scrollable>
        {entriesLoading && entries.length === 0 ? (
          <Spinner centered />
        ) : (
          entries.map((entry) => (
            <ListItem
              key={entry.slug}
              onClick={() => selectDoc(entry.slug)}
              selected={entry.slug === selectedSlug}
              padding="compact"
              bordered={false}
              className={entry.slug === selectedSlug ? styles.docItemActive : ""}
            >
              <div className={styles.docItemRow}>
                <FileTextIcon className={styles.docIcon} />
                <span className={styles.docTitle}>{entry.title}</span>
              </div>
            </ListItem>
          ))
        )}
      </PanelBody>
    </Panel>
  );
}
