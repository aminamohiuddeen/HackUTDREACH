// UTC formatting keeps server and client output identical.
export function fmtTime(iso: string) {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}Z`;
}
export function fmtCoord(lat: number, lon: number) {
  return `${Math.abs(lat).toFixed(5)}°${lat >= 0 ? "N" : "S"}  ${Math.abs(lon).toFixed(5)}°${lon >= 0 ? "E" : "W"}`;
}
