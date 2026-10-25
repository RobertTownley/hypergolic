export function granularityForDays(days: number): string {
  if (days <= 30) return "day";
  if (days <= 90) return "week";
  return "month";
}

export function formatCost(n: number): string {
  if (n < 0.01 && n > 0) return "<$0.01";
  return `$${n.toFixed(2)}`;
}
