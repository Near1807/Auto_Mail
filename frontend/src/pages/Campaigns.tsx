import clsx from "clsx";
import { Check, FileUp, FolderPlus, Inbox, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { Badge, Button, Card, EmptyState, Input, Modal, PageHeader } from "../components/ui";
import { useStore } from "../store";
import type { CampaignSummary } from "../types";

function formatDate(iso: string) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("fr-BE", { day: "numeric", month: "short", year: "numeric" });
}

export function CampaignsPage() {
  const { campaigns, refreshCampaigns, campaign, selectCampaign, go, job, dismissJob } = useStore();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<CampaignSummary | null>(null);
  const [deleting, setDeleting] = useState<CampaignSummary | null>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const create = async () => {
    try {
      const c = await api.createCampaign(name);
      await refreshCampaigns();
      selectCampaign(c.id);
      setCreating(false);
      setName("");
      toast.success(`Campagne « ${c.name} » créée`);
      go("recipients");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const importCsv = async (file: File) => {
    try {
      const c = await api.importCampaign(file);
      await refreshCampaigns();
      selectCampaign(c.id);
      toast.success(`« ${file.name} » importé`, { description: `${c.counts.total} adresse(s) dans le suivi.` });
    } catch (e) {
      toast.error("Import impossible", { description: (e as Error).message });
    }
  };

  const rename = async () => {
    if (!renaming) return;
    try {
      const c = await api.renameCampaign(renaming.id, name);
      if (campaign?.id === renaming.id) selectCampaign(c.id);
      await refreshCampaigns();
      setRenaming(null);
      toast.success("Campagne renommée");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const remove = async () => {
    if (!deleting) return;
    try {
      await api.deleteCampaign(deleting.id);
      if (job?.campaign_id === deleting.id) dismissJob();
      if (campaign?.id === deleting.id) selectCampaign(null);
      await refreshCampaigns();
      toast.success(`« ${deleting.name} » supprimée`);
      setDeleting(null);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  return (
    <>
      <PageHeader
        eyebrow="Étape 1"
        title="Campagnes"
        description="Une campagne regroupe un message, ses destinataires et son fichier de suivi. On n'écrit jamais deux fois à la même adresse dans une campagne."
        actions={
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".csv,text/csv"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importCsv(f);
                e.target.value = "";
              }}
            />
            <Button icon={<FileUp size={16} />} onClick={() => fileInput.current?.click()}>
              Importer un CSV
            </Button>
            <Button variant="primary" icon={<Plus size={16} />} onClick={() => { setName(""); setCreating(true); }}>
              Nouvelle campagne
            </Button>
          </>
        }
      />

      {campaigns.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Inbox size={30} />}
            title="Aucune campagne pour l'instant"
            action={
              <div className="flex gap-2">
                <Button variant="primary" icon={<FolderPlus size={16} />} onClick={() => setCreating(true)}>
                  Créer ma première campagne
                </Button>
                <Button icon={<FileUp size={16} />} onClick={() => fileInput.current?.click()}>
                  Reprendre un ancien suivi
                </Button>
              </div>
            }
          >
            Crée une campagne, ou importe le CSV d'un ancien envoi : les adresses déjà contactées seront automatiquement ignorées.
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {campaigns.map((c) => {
            const active = campaign?.id === c.id;
            const sending = job && job.campaign_id === c.id && (job.state === "running" || job.state === "paused");
            return (
              <div
                key={c.id}
                role="button"
                tabIndex={0}
                onClick={() => selectCampaign(c.id)}
                aria-label={`Campagne ${c.name}`}
                onDoubleClick={() => { selectCampaign(c.id); go("recipients"); }}
                onKeyDown={(e) => e.key === "Enter" && selectCampaign(c.id)}
                className={clsx(
                  "group relative cursor-pointer rounded-2xl border bg-surface p-5 text-left transition",
                  active ? "border-accent ring-4 ring-accent/12" : "border-line hover:border-muted/40 hover:shadow-sm",
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      {active && <span className="grid size-5 place-items-center rounded-full bg-accent text-accent-ink"><Check size={12} strokeWidth={3} /></span>}
                      <h3 className="truncate text-base font-bold">{c.name}</h3>
                    </div>
                    <p className="mt-1 truncate text-[13px] text-muted">{c.subject || "Pas encore d'objet"}</p>
                  </div>
                  <div className="relative" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="rounded-lg p-1.5 text-muted opacity-60 hover:bg-surface-2 hover:text-ink group-hover:opacity-100"
                      onClick={() => setMenu(menu === c.id ? null : c.id)}
                      aria-label="Actions"
                    >
                      <MoreHorizontal size={18} />
                    </button>
                    {menu === c.id && (
                      <div className="absolute right-0 z-10 mt-1 w-40 overflow-hidden rounded-xl border border-line bg-surface py-1 shadow-xl" onMouseLeave={() => setMenu(null)}>
                        <button className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-surface-2" onClick={() => { setMenu(null); setName(c.name); setRenaming(c); }}>
                          <Pencil size={14} /> Renommer
                        </button>
                        <button className="flex w-full items-center gap-2 px-3 py-2 text-sm text-bad hover:bg-bad-soft" onClick={() => { setMenu(null); setDeleting(c); }}>
                          <Trash2 size={14} /> Supprimer
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <div className="mt-5 flex flex-wrap items-center gap-1.5">
                  {sending && <Badge tone="accent">Envoi en cours</Badge>}
                  <Badge tone={c.counts.sent ? "ok" : "neutral"}>{c.counts.sent} envoyé{c.counts.sent > 1 ? "s" : ""}</Badge>
                  {c.counts.errors > 0 && <Badge tone="bad">{c.counts.errors} erreur{c.counts.errors > 1 ? "s" : ""}</Badge>}
                  {c.counts.replies > 0 && <Badge tone="info">{c.counts.replies} réponse{c.counts.replies > 1 ? "s" : ""}</Badge>}
                </div>
                <div className="mt-3 text-[11px] text-muted">Modifiée le {formatDate(c.updated || c.created)}</div>
              </div>
            );
          })}
        </div>
      )}

      {campaign && campaigns.length > 0 && (
        <div className="mt-6 flex items-center justify-between rounded-2xl bg-accent-soft/60 px-5 py-4">
          <div className="text-sm">
            Campagne active : <strong>{campaign.name}</strong>
          </div>
          <Button variant="primary" size="sm" onClick={() => go("recipients")}>
            Continuer vers les destinataires →
          </Button>
        </div>
      )}

      <Modal
        open={creating}
        onClose={() => setCreating(false)}
        title="Nouvelle campagne"
        footer={
          <>
            <Button variant="ghost" onClick={() => setCreating(false)}>Annuler</Button>
            <Button variant="primary" onClick={create} disabled={!name.trim()}>Créer</Button>
          </>
        }
      >
        <Input autoFocus placeholder="ex. Hikes 2026-2027" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && create()} />
        <p className="mt-2 text-xs text-muted">Le nom sert aussi de nom de dossier ; tu pourras le changer.</p>
      </Modal>

      <Modal
        open={!!renaming}
        onClose={() => setRenaming(null)}
        title="Renommer la campagne"
        footer={
          <>
            <Button variant="ghost" onClick={() => setRenaming(null)}>Annuler</Button>
            <Button variant="primary" onClick={rename} disabled={!name.trim()}>Renommer</Button>
          </>
        }
      >
        <Input autoFocus value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => e.key === "Enter" && name.trim() && rename()} />
      </Modal>

      <Modal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title="Supprimer la campagne ?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDeleting(null)}>Annuler</Button>
            <Button variant="danger" icon={<Trash2 size={15} />} onClick={remove}>Supprimer définitivement</Button>
          </>
        }
      >
        <p className="text-sm">
          « <strong>{deleting?.name}</strong> » sera supprimée avec son message, ses pièces jointes et son fichier de suivi
          {deleting && deleting.counts.total > 0 && <> ({deleting.counts.total} adresse{deleting.counts.total > 1 ? "s" : ""})</>}.
        </p>
        <p className="mt-2 text-sm text-muted">Sans le suivi, Auto Mail ne saura plus à qui tu as déjà écrit. Exporte-le d'abord si besoin.</p>
      </Modal>
    </>
  );
}
