import { useEffect, useState } from "react";
import { api } from "../api";
import type { Analysis } from "../types";

/** Analyse des destinataires, recalculée (avec un léger délai) quand le texte change. */
export function useAnalysis(campaignId: string | undefined, raw: string | undefined, refreshKey = 0) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!campaignId) return;
    let cancelled = false;
    setLoading(true);
    const t = window.setTimeout(async () => {
      try {
        const result = await api.analyze(campaignId, raw ?? "");
        if (!cancelled) setAnalysis(result);
      } catch {
        /* l'erreur réseau est signalée ailleurs */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 250);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
  }, [campaignId, raw, refreshKey]);

  return { analysis, loading };
}
