export function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const isToday =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate();

  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (isToday) return time;

  const sameYear = d.getFullYear() === now.getFullYear();
  const date = d.toLocaleDateString([], {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
  return `${date}, ${time}`;
}
