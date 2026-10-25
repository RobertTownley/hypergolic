/** Join class names, dropping the absent ones — `styles[key]` misses included. */
export function cx(...names: (string | false | undefined | null)[]): string {
  return names.filter(Boolean).join(" ");
}
