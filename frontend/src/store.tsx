import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api } from "./api";
import type { CampaignDetail, CampaignSummary, DraftData, JobEvent, JobSnapshot, Settings } from "./types";

export type Page = "campaigns" | "recipients" | "message" | "send" | "tracking" | "settings";
type SaveState = "idle" | "saving" | "saved" | "error";

type Store = {
  page: Page;
  go: (p: Page) => void;
  settings: Settings | null;
  setSettings: (s: Settings) => void;
  campaigns: CampaignSummary[];
  refreshCampaigns: () => Promise<void>;
  campaign: CampaignDetail | null;
  selectCampaign: (id: string | null) => void;
  reloadCampaign: () => Promise<void>;
  setCampaign: (c: CampaignDetail) => void;
  updateDraft: (changes: Partial<DraftData>) => void;
  flushDraft: () => Promise<void>;
  saveState: SaveState;
  job: JobSnapshot | null;
  events: JobEvent[];
  followJob: (job: JobSnapshot) => void;
  setJob: (job: JobSnapshot) => void;
  theme: Settings["theme"];
  setTheme: (t: Settings["theme"]) => void;
};

const Ctx = createContext<Store | null>(null);

export const useStore = () => {
  const store = useContext(Ctx);
  if (!store) throw new Error("useStore hors du StoreProvider");
  return store;
};

function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function writeLocal(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* stockage indisponible */
  }
}

function applyTheme(theme: Settings["theme"]) {
  const dark = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  writeLocal("automail-theme", theme);
}

export function StoreProvider({ children }: { children: ReactNode }) {
  const [page, setPage] = useState<Page>((readLocal("automail-page") as Page) || "campaigns");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [campaigns, setCampaigns] = useState<CampaignSummary[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(readLocal("automail-campaign"));
  const [campaign, setCampaign] = useState<CampaignDetail | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [theme, setThemeState] = useState<Settings["theme"]>((readLocal("automail-theme") as Settings["theme"]) || "system");

  const pending = useRef<Partial<DraftData>>({});
  const timer = useRef<number | undefined>(undefined);
  const campaignRef = useRef<CampaignDetail | null>(null);
  campaignRef.current = campaign;
  const source = useRef<EventSource | null>(null);

  const go = useCallback((p: Page) => {
    setPage(p);
    writeLocal("automail-page", p);
  }, []);

  const refreshCampaigns = useCallback(async () => {
    setCampaigns(await api.campaigns());
  }, []);

  const flushDraft = useCallback(async () => {
    window.clearTimeout(timer.current);
    const current = campaignRef.current;
    const changes = pending.current;
    if (!current || Object.keys(changes).length === 0) return;
    pending.current = {};
    setSaveState("saving");
    try {
      await api.saveDraft(current.id, changes);
      setSaveState("saved");
    } catch (e) {
      pending.current = { ...changes, ...pending.current };
      setSaveState("error");
      toast.error("Brouillon non enregistré", { description: (e as Error).message });
    }
  }, []);

  const updateDraft = useCallback(
    (changes: Partial<DraftData>) => {
      setCampaign((c) => (c ? { ...c, draft: { ...c.draft, ...changes } } : c));
      pending.current = { ...pending.current, ...changes };
      setSaveState("saving");
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(flushDraft, 600);
    },
    [flushDraft],
  );

  const selectCampaign = useCallback(
    (id: string | null) => {
      void flushDraft();
      setCurrentId(id);
      writeLocal("automail-campaign", id);
    },
    [flushDraft],
  );

  const reloadCampaign = useCallback(async () => {
    if (!currentId) return;
    try {
      setCampaign(await api.campaign(currentId));
    } catch {
      setCampaign(null);
      setCurrentId(null);
      writeLocal("automail-campaign", null);
    }
  }, [currentId]);

  useEffect(() => {
    setSaveState("idle");
    if (currentId) void reloadCampaign();
    else setCampaign(null);
  }, [currentId, reloadCampaign]);

  const subscribe = useCallback((snapshot: JobSnapshot, after: number) => {
    source.current?.close();
    const es = new EventSource(`/api/jobs/${snapshot.id}/events?after=${after}`);
    source.current = es;
    es.onmessage = (msg) => {
      const event = JSON.parse(msg.data) as JobEvent;
      setEvents((prev) => (prev.some((e) => e.seq === event.seq) ? prev : [...prev, event]));
      setJob(event.progress);
      if (event.type === "warning") toast.warning(event.message);
      if (event.type === "label") (event.ok ? toast.success : toast.error)(event.message);
      if (event.type === "done") {
        es.close();
        if (event.ok) toast.success(event.message, { description: `${event.progress.sent} envoyé(s), ${event.progress.errors} erreur(s)` });
        else toast.error(event.message);
        void refreshCampaigns();
      }
    };
    es.onerror = () => {
      // EventSource se reconnecte seul (Last-Event-ID) ; on ferme seulement si la tâche est finie.
      if (es.readyState === EventSource.CLOSED) source.current = null;
    };
  }, [refreshCampaigns]);

  const followJob = useCallback(
    (snapshot: JobSnapshot) => {
      setJob(snapshot);
      setEvents([]);
      subscribe(snapshot, 0);
    },
    [subscribe],
  );

  const setTheme = useCallback((t: Settings["theme"]) => {
    setThemeState(t);
    applyTheme(t);
    void api.saveSettings({ theme: t }).then(setSettings).catch(() => undefined);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const s = await api.settings();
        setSettings(s);
        setThemeState(s.theme);
        applyTheme(s.theme);
        await refreshCampaigns();
        const current = await api.currentJob();
        if (current) {
          setJob(current);
          const log = await api.jobLog(current.id);
          setEvents(log);
          if (!["done", "failed", "cancelled"].includes(current.state)) subscribe(current, log.at(-1)?.seq ?? 0);
        }
      } catch (e) {
        toast.error("Impossible de joindre le moteur", { description: (e as Error).message });
      }
    })();
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applyTheme((readLocal("automail-theme") as Settings["theme"]) || "system");
    media.addEventListener("change", onChange);
    const beforeUnload = () => void flushDraft();
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      media.removeEventListener("change", onChange);
      window.removeEventListener("beforeunload", beforeUnload);
      source.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const value = useMemo<Store>(
    () => ({
      page, go, settings, setSettings, campaigns, refreshCampaigns, campaign, selectCampaign, reloadCampaign,
      setCampaign, updateDraft, flushDraft, saveState, job, events, followJob, setJob, theme, setTheme,
    }),
    [page, go, settings, campaigns, refreshCampaigns, campaign, selectCampaign, reloadCampaign, updateDraft,
      flushDraft, saveState, job, events, followJob, theme, setTheme],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
