// Pont vers l'application de bureau (pywebview). Absent dans un navigateur (dev).
type DesktopApi = {
  save_export: (campaignId: string) => Promise<{ ok: boolean; path?: string; cancelled?: boolean; message?: string }>;
};

declare global {
  interface Window {
    pywebview?: { api?: Partial<DesktopApi> };
  }
}

export function desktopApi(): Partial<DesktopApi> | null {
  return window.pywebview?.api ?? null;
}
