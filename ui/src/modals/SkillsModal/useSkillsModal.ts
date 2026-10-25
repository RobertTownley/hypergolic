export function sourceLabel(source: string): string {
  switch (source) {
    case "user": return "User";
    case "user-project": return "User-Project";
    case "project": return "Project";
    default: return source;
  }
}
