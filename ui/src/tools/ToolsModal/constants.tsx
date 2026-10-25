export function mcpDisplayName(name: string): string {
  const colonIdx = name.indexOf(": ");
  return colonIdx >= 0 ? name.slice(colonIdx + 2) : name;
}
