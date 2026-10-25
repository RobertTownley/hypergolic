import styles from "./ToolsModal.module.css";

export interface SchemaProperty {
  type?: string | string[];
  description?: string;
  default?: unknown;
  enum?: string[];
  anyOf?: Array<{ type?: string; enum?: string[] }>;
  items?: { type?: string; enum?: string[]; $ref?: string };
}

function formatEnum(values: string[]): string {
  return values.map((v) => `"${v}"`).join(" | ");
}

function formatBranch(branch: { type?: string; enum?: string[] }): string {
  if (branch.enum) return formatEnum(branch.enum);
  return branch.type ?? "?";
}

function formatType(prop: SchemaProperty): string {
  if (prop.anyOf) {
    const types = prop.anyOf
      .filter((a) => a.type !== "null")
      .map(formatBranch);
    return types.join(" | ") || "any";
  }
  if (prop.enum) return formatEnum(prop.enum);
  if (prop.type === "array") {
    if (prop.items?.enum) {
      return `(${formatEnum(prop.items.enum)})[]`;
    }
    const itemType = prop.items?.type ?? "any";
    return `${itemType}[]`;
  }
  if (Array.isArray(prop.type)) return prop.type.filter((t) => t !== "null").join(" | ");
  return prop.type ?? "any";
}

export function ToolParams({ schema }: { schema: Record<string, unknown> }) {
  const properties = schema.properties as Record<string, SchemaProperty> | undefined;
  const required = new Set((schema.required as string[]) ?? []);

  if (!properties || Object.keys(properties).length === 0) return null;

  return (
    <div className={styles.params}>
      {Object.entries(properties).map(([name, prop]) => (
        <div key={name} className={styles.paramRow}>
          <div className={styles.paramSignature}>
            <span className={styles.paramName}>{name}</span>
            {!required.has(name) && <span className={styles.paramOptional}>?</span>}
            <span className={styles.paramType}>{formatType(prop)}</span>
            {prop.default !== undefined && prop.default !== null && (
              <span className={styles.paramDefault}>= {JSON.stringify(prop.default)}</span>
            )}
          </div>
          {prop.description && <div className={styles.paramDesc}>{prop.description}</div>}
        </div>
      ))}
    </div>
  );
}
