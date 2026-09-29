/** Display formatting only. Stored values are never rounded; these helpers produce strings for the screen. */
export function pct(p: number, digits?: number): string {
  const v = p * 100;
  const d = digits ?? (v >= 10 ? 1 : v >= 1 ? 1 : v >= 0.1 ? 2 : 3);
  if (p === 0) return "0%";
  return `${v.toFixed(d)}%`;
}


export function rating(r: number): string {
  return r.toFixed(0);
}




export function mmdd(iso: string): string {
  return `${iso.slice(5, 7)}.${iso.slice(8, 10)}`;
}
