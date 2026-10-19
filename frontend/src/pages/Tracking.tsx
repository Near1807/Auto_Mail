import clsx from "clsx";
import { ArrowDown, ArrowUp, Download, FolderOpen, MailCheck, MessageSquareReply, RefreshCw, Search, Send, Table2, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { desktopApi } from "../lib/desktop";
import { Badge, Button, Card, EmptyState, Input, PageHeader, Segmented, Spinner, Stat } from "../components/ui";
import { useStore } from "../store";
import type { Tracking } from "../types";

type Filter = "all" | "Envoyé" | "Erreur" | "replied" | "waiting";

const LABELS: Record<string, string> = {
  email: "Adresse",
  status: "Statut",
  reponse: "Réponse",
  date: "Date",
  objet: "Objet",
  erreur: "Erreur",
};

function ReplyCell({ value, onSave }: { value: string; onSave: (v: string) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commit = async () => {
    setEditing(false);
    if (draft === value) return;
    setSaving(true);
    try {
      await onSave(draft);
    } catch {
      setDraft(value);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") void commit();
          if (e.key === "Escape") { setDraft(value); setEditing(false); }
        }}
        className="h-8 w-full min-w-[180px] rounded-lg border border-accent bg-surface px-2 text-[13px] ring-4 ring-accent/15 outline-none"
      />
    );
  }
  return (
    <button
      onClick={() => setEditing(true)}
      title="Cliquer pour modifier"
      className={clsx(
        "flex h-8 w-full min-w-[180px] items-center gap-2 rounded-lg px-2 text-left text-[13px] transition hover:bg-surface-2 hover:ring-1 hover:ring-line",
        !draft && "text-muted/60",
      )}
    >
      {saving && <Spinner size={12} />}
      <span className="truncate">{draft || "Ajouter une note…"}</span>
    </button>
  );
}

export function TrackingPage() {
  const { campaign, job, refreshCampaigns } = useStore();
  const [data, setData] = useState<Tracking | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ col: string; dir: 1 | -1 }>({ col: "date", dir: -1 });
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    if (!campaign) return;
    try {
      setData(await api.tracking(campaign.id));
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [campaign]);

  useEffect(() => { void load(); }, [load, job?.sent, job?.errors]);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toLowerCase();
    return data.rows
      .filter((r) => {
        if (filter === "Envoyé" || filter === "Erreur") return r.status === filter;
        if (filter === "replied") return !!r.reponse?.trim();
        if (filter === "waiting") return r.status === "Envoyé" && !r.reponse?.trim();
        return true;
      })
      .filter((r) => !q || Object.values(r).some((v) => v?.toLowerCase().includes(q)))
      .sort((a, b) => (a[sort.col] ?? "").localeCompare(b[sort.col] ?? "", "fr", { numeric: true }) * sort.dir);
  }, [data, filter, query, sort]);

  if (!campaign) return null;

  const saveReply = async (email: string, value: string) => {
    try {
      await api.editCell(campaign.id, email, value);
      setData((d) => d && { ...d, rows: d.rows.map((r) => (r.email === email ? { ...r, reponse: value } : r)),
        counts: { ...d.counts, replies: d.rows.filter((r) => (r.email === email ? value : r.reponse)?.trim()).length } });
      void refreshCampaigns();
    } catch (e) {
      toast.error("Non enregistré", { description: (e as Error).message });
      throw e;
    }
  };

  const checkReplies = async () => {
    setChecking(true);
    try {
      const r = await api.checkReplies(campaign.id);
      await load();
      void refreshCampaigns();
      if (r.updated.length) toast.success(`${r.updated.length} nouvelle(s) réponse(s) trouvée(s)`, { description: r.updated.slice(0, 5).join(", ") + (r.updated.length > 5 ? "…" : "") });
      else toast.info(r.found ? "Pas de nouvelle réponse (les réponses déjà notées ne sont pas écrasées)." : "Aucune réponse trouvée dans les fils de ce libellé.");
    } catch (e) {
      toast.error("Vérification impossible", { description: (e as Error).message });
    } finally {
      setChecking(false);
    }
  };

  const exportCsv = async () => {
    const desktop = desktopApi();
    if (!desktop?.save_export) {
      // Navigateur (dev) : téléchargement classique.
      const link = document.createElement("a");
      link.href = api.exportUrl(campaign.id);
      link.download = `suivi-${campaign.id}.csv`;
      link.click();
      return;
    }
    try {
      const r = await desktop.save_export(campaign.id);
      if (r.ok) toast.success("Suivi exporté", { description: r.path });
      else if (!r.cancelled) toast.error("Export impossible", { description: r.message });
    } catch (e) {
      toast.error("Export impossible", { description: String(e) });
    }
  };

  const openFolder = async () => {
    try {
      await api.openFolder(campaign.id);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const columns = data?.columns ?? [];
  const counts = data?.counts;

  return (
    <>
      <PageHeader
        eyebrow={campaign.name}
        title="Suivi"
        description={<>Le fichier <code className="rounded bg-surface-2 px-1 font-mono text-xs">suivi.csv</code> de la campagne. La colonne Réponse se modifie directement dans le tableau.</>}
        actions={
          <>
            <Button icon={checking ? <Spinner /> : <MessageSquareReply size={16} />} onClick={checkReplies} disabled={checking || !campaign.draft.label} title={campaign.draft.label ? `Parcourt les fils du libellé « ${campaign.draft.label} »` : "Ajoute un libellé à la campagne pour pouvoir vérifier les réponses"}>
              Vérifier les réponses
            </Button>
            <Button icon={<Download size={16} />} onClick={exportCsv}>Exporter</Button>
            <Button variant="ghost" icon={<FolderOpen size={16} />} onClick={openFolder}>Ouvrir le dossier</Button>
          </>
        }
      />

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Adresses suivies" value={counts?.total ?? 0} icon={<Table2 size={14} />} />
        <Stat label="Envoyés" value={counts?.sent ?? 0} tone="ok" icon={<Send size={14} />} />
        <Stat label="Erreurs" value={counts?.errors ?? 0} tone="bad" icon={<XCircle size={14} />} />
        <Stat
          label="Réponses"
          value={<>{counts?.replies ?? 0}{counts && counts.sent > 0 && <span className="ml-1.5 text-sm font-semibold text-muted">{Math.round((counts.replies / counts.sent) * 100)} %</span>}</>}
          tone="info"
          icon={<MailCheck size={14} />}
        />
      </div>

      {data && data.rows.length === 0 ? (
        <Card>
          <EmptyState icon={<Table2 size={30} />} title="Rien d'envoyé pour l'instant">
            Chaque mail envoyé (ou en erreur) apparaîtra ici, avec sa date et son objet.
          </EmptyState>
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line p-3">
            <Segmented<Filter>
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "Tous" },
                { value: "Envoyé", label: "Envoyés" },
                { value: "Erreur", label: "Erreurs" },
                { value: "replied", label: "Avec réponse" },
                { value: "waiting", label: "Sans réponse" },
              ]}
            />
            <div className="flex items-center gap-2">
              <div className="relative">
                <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
                <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher…" className="h-9 w-60 pl-9" />
              </div>
              <Button variant="ghost" size="sm" onClick={load} title="Recharger"><RefreshCw size={15} /></Button>
            </div>
          </div>
          <div className="max-h-[calc(100vh-380px)] min-h-[200px] overflow-auto">
            <table className="w-full border-collapse text-[13px]">
              <thead className="sticky top-0 z-[1] bg-surface">
                <tr className="border-b border-line">
                  {columns.map((c) => (
                    <th
                      key={c}
                      onClick={() => setSort((s) => ({ col: c, dir: s.col === c ? (-s.dir as 1 | -1) : 1 }))}
                      className="cursor-pointer px-3 py-2.5 text-left text-xs font-bold whitespace-nowrap text-muted select-none hover:text-ink"
                    >
                      <span className="inline-flex items-center gap-1">
                        {LABELS[c] ?? c}
                        {sort.col === c && (sort.dir === 1 ? <ArrowUp size={12} /> : <ArrowDown size={12} />)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.email} className="border-b border-line/70 last:border-0 hover:bg-surface-2/50">
                    {columns.map((c) => (
                      <td key={c} className={clsx("px-3 py-1.5 align-middle", c === "reponse" ? "w-[28%] px-1.5" : "")}>
                        {c === "email" ? (
                          <span className="font-mono text-xs">{r.email}</span>
                        ) : c === "status" ? (
                          r.status === "Envoyé" ? <Badge tone="ok">Envoyé</Badge> : r.status === "Erreur" ? <Badge tone="bad">Erreur</Badge> : r.status ? <Badge>{r.status}</Badge> : null
                        ) : c === "reponse" ? (
                          <ReplyCell value={r.reponse ?? ""} onSave={(v) => saveReply(r.email, v)} />
                        ) : c === "erreur" ? (
                          <span className="line-clamp-2 text-xs text-bad" title={r.erreur}>{r.erreur}</span>
                        ) : c === "date" ? (
                          <span className="whitespace-nowrap text-muted tabular-nums">{r.date}</span>
                        ) : (
                          <span className="line-clamp-1 max-w-[260px]" title={r[c]}>{r[c]}</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <p className="py-10 text-center text-sm text-muted">Aucune ligne ne correspond.</p>}
          </div>
        </Card>
      )}
    </>
  );
}
