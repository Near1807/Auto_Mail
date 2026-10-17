// Même logique que core/message.py : {variable} remplacée, inconnue laissée telle quelle.
const VARIABLE_RE = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

export function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (ch) =>
    ch === "&" ? "&amp;" : ch === "<" ? "&lt;" : ch === ">" ? "&gt;" : ch === '"' ? "&quot;" : "&#x27;",
  );
}

export function render(template: string, vars: Record<string, string>, escape = false): string {
  return template.replace(VARIABLE_RE, (match, name: string) => {
    const key = name.toLowerCase();
    if (!(key in vars)) return match;
    const value = vars[key] ?? "";
    return escape ? escapeHtml(value) : value;
  });
}

export function usedVariables(...templates: string[]): string[] {
  const found = new Set<string>();
  for (const t of templates) for (const m of t.matchAll(VARIABLE_RE)) found.add(m[1].toLowerCase());
  return [...found];
}

export function textToHtml(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((p) => `<p>${escapeHtml(p).replace(/\n/g, "<br>")}</p>`)
    .join("\n");
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} o`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} Ko`;
  return `${(size / 1024 / 1024).toFixed(1)} Mo`;
}

export function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, "0")}`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")}`;
}

export function plural(n: number, one: string, many = one + "s"): string {
  return `${n.toLocaleString("fr-BE")} ${n > 1 ? many : one}`;
}
