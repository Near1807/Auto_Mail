import clsx from "clsx";
import { AlertTriangle, ClipboardPaste, Eraser, RotateCcw, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { Badge, Button, Card, PageHeader, Spinner, Textarea, type Tone } from "../components/ui";
import { plural } from "../lib/render";
import { useAnalysis } from "../lib/useAnalysis";
import { useStore } from "../store";
import type { RecipientStatus } from "../types";

type Filter = "all" | RecipientStatus | "invalid";

const STATUS: Record<RecipientStatus, { label: string; tone: Tone }> = {
  new: { label: "à envoyer", tone: "accent" },
  retry: { label: "erreur, retentée", tone: "warn" },
  sent: { label: "déjà envoyée", tone: "neutral" },
};

const EXAMPLE = `Collez ici, dans n'importe quel format :

jean@ecole.be, marie@asbl.be; contact@olln.be
['a@b.be', 'c@d.be']
Jean Dupont <jean.dupont@exemple.be>
mailto:info@exemple.be

…ou un tableau copié d'Excel (email + colonnes → variables {prenom}, {nom}…)`;

export function RecipientsPage() {
  const { campaign, updateDraft, go } = useStore();
  const raw = campaign?.draft.recipients_raw ?? "";
  const { analysis, loading } = useAnalysis(campaign?.id, raw);
  const [filter, setFilter] = useState<Filter>("all");

  const chips = useMemo(() => {
    if (!analysis) return [];
    const list: { key: string; label: string; status: Filter; fields?: Record<string, string> }[] = analysis.recipients.map((r) => ({
      key: r.email,
      label: r.email,
      status: r.status,
      fields: r.fields,
    }));
    analysis.invalid.forEach((v, i) => list.push({ key: `invalid-${i}`, label: v, status: "invalid" }));
    return filter === "all" ? list : list.filter((c) => c.status === filter);
  }, [analysis, filter]);

  if (!campaign) return null;
  const counts = analysis?.counts;

  const paste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      updateDraft({ recipients_raw: raw ? `${raw.trimEnd()}\n${text}` : text });
    } catch {
      /* presse-papiers refusé : le collage clavier marche toujours */
    }
  };

  const tiles: { key: Filter; label: string; value: number; tone: Tone }[] = counts
    ? [
        { key: "all", label: "Valides", value: counts.valid, tone: "neutral" },
        { key: "new", label: "Nouvelles", value: counts.new, tone: "accent" },
        { key: "retry", label: "En erreur (retentées)", value: counts.retry, tone: "warn" },
        { key: "sent", label: "Déjà envoyées (ignorées)", value: counts.already_sent, tone: "neutral" },
        { key: "invalid", label: "Invalides", value: counts.invalid, tone: "bad" },
      ]
    : [];

  return (
    <>
      <PageHeader
        eyebrow={campaign.name}
        title="Destinataires"
        description="Colle tes adresses telles quelles : Auto Mail trouve les adresses, écarte les doublons et celles déjà contactées dans cette campagne."
        actions={
          <>
            <Button icon={<ClipboardPaste size={16} />} onClick={paste}>Coller</Button>
            <Button variant="ghost" icon={<Eraser size={16} />} disabled={!raw} onClick={() => updateDraft({ recipients_raw: "" })}>
              Vider
            </Button>
          </>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <Card className="flex flex-col p-1.5">
          <Textarea
            value={raw}
            spellCheck={false}
            onChange={(e) => updateDraft({ recipients_raw: e.target.value })}
            placeholder={EXAMPLE}
            className="min-h-[460px] flex-1 resize-none border-0 font-mono [tab-size:12] text-[13px] leading-relaxed focus:ring-0"
          />
          {analysis && analysis.columns.length > 0 && (
            <div className="m-1.5 flex flex-wrap items-center gap-1.5 rounded-xl bg-info-soft px-3 py-2.5 text-[13px] text-info">
              <Sparkles size={15} />
              <span className="font-semibold">Tableau détecté. Variables disponibles :</span>
              {analysis.columns.map((c) => (
                <code key={c} className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-xs text-ink">{`{${c}}`}</code>
              ))}
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <div className="rounded-2xl bg-ink p-5 text-bg">
            <div className="flex items-center justify-between text-xs font-semibold opacity-70">
              <span>Seront envoyés</span>
              {loading && <Spinner size={14} />}
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-5xl font-extrabold tabular-nums">{counts?.to_send ?? 0}</span>
              <span className="text-sm opacity-70">{counts?.to_send === 1 ? "mail" : "mails"}</span>
            </div>
            {counts && counts.to_send > 500 && (
              <div className="mt-3 flex items-start gap-2 rounded-xl bg-white/10 p-3 text-xs">
                <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warn" />
                Gmail limite à environ 500 envois par jour : répartis l'envoi sur plusieurs jours.
              </div>
            )}
            {counts && counts.duplicates > 0 && (
              <div className="mt-3 text-xs opacity-70">{plural(counts.duplicates, "doublon")} retiré{counts.duplicates > 1 ? "s" : ""} de la liste collée.</div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {tiles.map((t) => (
              <button
                key={t.key}
                onClick={() => setFilter(filter === t.key ? "all" : t.key)}
                className={clsx(
                  "rounded-xl border p-3 text-left transition",
                  filter === t.key && t.key !== "all" ? "border-accent bg-accent-soft/50" : "border-line bg-surface hover:border-muted/40",
                )}
              >
                <div className="text-[11px] leading-tight font-semibold text-muted">{t.label}</div>
                <div className={clsx("mt-1 text-xl font-extrabold tabular-nums", t.tone === "bad" && t.value > 0 && "text-bad", t.tone === "warn" && t.value > 0 && "text-warn")}>
                  {t.value}
                </div>
              </button>
            ))}
          </div>

          <Card className="p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold">{filter === "all" ? "Toutes les adresses" : tiles.find((t) => t.key === filter)?.label}</h3>
              {filter !== "all" && (
                <button className="inline-flex items-center gap-1 text-xs font-semibold text-muted hover:text-ink" onClick={() => setFilter("all")}>
                  <RotateCcw size={12} /> Tout afficher
                </button>
              )}
            </div>
            {chips.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted">{raw ? "Rien dans cette catégorie." : "Les adresses apparaîtront ici."}</p>
            ) : (
              <div className="flex max-h-[320px] flex-wrap gap-1.5 overflow-auto pr-1">
                {chips.map((c) => {
                  const tone: Tone = c.status === "invalid" ? "bad" : STATUS[c.status as RecipientStatus].tone;
                  const title = c.status === "invalid" ? "Adresse invalide" : `${STATUS[c.status as RecipientStatus].label}${
                    c.fields && Object.keys(c.fields).length ? "\n" + Object.entries(c.fields).map(([k, v]) => `${k} : ${v}`).join("\n") : ""}`;
                  return (
                    <span
                      key={c.key}
                      title={title}
                      className={clsx(
                        "inline-flex max-w-full items-center gap-1.5 truncate rounded-lg border px-2 py-1 font-mono text-xs",
                        tone === "accent" && "border-accent/25 bg-accent-soft/50 text-ink",
                        tone === "warn" && "border-warn/30 bg-warn-soft text-warn",
                        tone === "neutral" && "border-line bg-surface-2 text-muted line-through decoration-muted/50",
                        tone === "bad" && "border-bad/30 bg-bad-soft text-bad",
                      )}
                    >
                      {c.label}
                    </span>
                  );
                })}
              </div>
            )}
            <div className="mt-4 flex flex-wrap gap-1.5 border-t border-line pt-3 text-[11px]">
              <Badge tone="accent">nouvelle</Badge>
              <Badge tone="warn">erreur → retentée</Badge>
              <Badge tone="neutral"><s>déjà envoyée</s></Badge>
              <Badge tone="bad">invalide</Badge>
            </div>
          </Card>

          <div className="flex justify-end">
            <Button variant="primary" onClick={() => go("message")} disabled={!counts?.to_send}>
              Écrire le message →
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
