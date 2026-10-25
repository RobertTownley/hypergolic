import type { SlashCommand } from "./slashCommands";
import styles from "./ChatInput.module.css";

interface SlashMenuProps {
  commands: SlashCommand[];
  selectedIndex: number;
  onSelect: (command: SlashCommand) => void;
  onHover: (index: number) => void;
}

export function SlashMenu({ commands, selectedIndex, onSelect, onHover }: SlashMenuProps) {
  return (
    <div className={styles.slashMenu} role="listbox" aria-label="Commands">
      {commands.map((cmd, i) => (
        <button
          key={cmd.name}
          type="button"
          role="option"
          aria-selected={i === selectedIndex}
          className={`${styles.slashItem} ${i === selectedIndex ? styles.slashItemSelected : ""}`}
          onMouseEnter={() => onHover(i)}
          onMouseDown={(e) => {
            e.preventDefault();
            onSelect(cmd);
          }}
        >
          <span className={styles.slashItemName}>
            /{cmd.name}
            {cmd.argHint && <span className={styles.slashItemArgs}> {cmd.argHint}</span>}
          </span>
          <span className={styles.slashItemDescription}>{cmd.description}</span>
        </button>
      ))}
    </div>
  );
}
