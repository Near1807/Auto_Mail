import clsx from "clsx";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  FlaskConical,
  Pause,
  Play,
  Rocket,
  Ban,
  Tag,
  TriangleAlert,
  XCircle,
  SkipForward,
  Info,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { Badge, Button, Card, Field, Input, Modal, PageHeader, Spinner, Stat } from "../components/ui";
import { formatBytes, formatDuration, plural } from "../lib/render";
import { useAnalysis } from "../lib/useAnalysis";
import { useStore } from "../store";
import type { JobEvent, SendSummary } from "../types";

function LogLine({ e }: { e: JobEvent }) {
  const icon =
    e.type === "sent" ? <CheckCircle2 size={15} className="text-ok" /> :
    e.type === "error" ? <XCircle size={15} className="text-bad" /> :
    e.type === "skipped" ? <SkipForward size={15} className="text-muted" /> :
    e.type === "warning" ? <TriangleAlert size={15} className="text-warn" /> :
    e.type === "label" ? <Tag size={15} className={e.ok ? "text-info" : "text-bad"} /> :
    <Info size={15} className="text-muted" />;
  const text =
    e.type === "sent" ? e.email :
    e.type === "start" ? `Connexion à Gmail en tant que ${(e as JobEvent & { sender?: string }).sender ?? ""}` :
    e.type === "paused" ? "Pause" :
    e.type === "resumed" ? "Reprise" :
    e.type === "error" || e.type === "skipped" ? e.email : e.message;
  return (
    <div className={clsx("flex items-start gap-3 px-4 py-2 text-[13px]", e.type === "error" && "bg-bad-soft/40")}>
      <span className="w-14 shrink-0 font-mono text-[11px] leading-5 text-muted">{e.time}</span>
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className={clsx("break-all", e.type === "sent" || e.type === "error" ? "font-mono text-xs" : "")}>{text}</span>
        {(e.type === "error" || e.type === "skipped") && e.message && <span className="block text-xs text-bad">{e.message}</span>}
      </span>
    </div>
  );
}

export function SendPage() {
  const { campaign, updateDraft, flushDraft, settings, setSettings, job, events, followJob, setJob, dismissJob, go, reloadCampaign } = useStore();
  const { analysis } = useAnalysis(campaign?.id, campaign?.draft.recipients_raw, job?.state === "done" ? job.sent : 0);
  const [summary, setSummary] = useState<SendSummary | null>(null);
  const [testing, setTesting] = useState(false);
  const [starting, setStarting] = useState(false);
  const [delay, setDelay] = useState(settings?.delay_seconds ?? 3);
  const logEnd = useRef<HTMLDivElement>(null);

  // Corps entre accolades : un effet ne doit rien renvoyer d'autre qu'une fonction de nettoyage.
  // (Dans WebView2, scrollIntoView() renvoie une Promise : renvoyée ici, React l'appelait
  // comme nettoyage → « TypeError: p is not a function » → page blanche.)
  useEffect(() => {
    setDelay(settings?.delay_seconds ?? 3);
  }, [settings?.delay_seconds]);
  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "nearest" });
  }, [events.length]);

  if (!campaign) return null;
  const draft = campaign.draft;
  const mine = job && job.campaign_id === campaign.id;
  const active = mine && (job.state === "running" || job.state === "paused");
  const otherActive = job && !mine && (job.state === "running" || job.state === "paused");
  const toSend = analysis?.counts.to_send ?? 0;
  const done = job ? job.sent + job.errors + job.skipped : 0;
  const pct = job && job.total ? (done / job.total) * 100 : 0;

  const saveDelay = async (value: number) => {
    setDelay(value);
    try {
      setSettings(await api.saveSettings({ delay_seconds: value }));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const openConfirm = async () => {
    await flushDraft();
    try {
      setSummary(await api.sendSummary(campaign.id));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const sendTest = async () => {
    await flushDraft();
    setTesting(true);
    try {
      const r = await api.testSend(campaign.id);
      toast.success(r.message, { description: "Ce test n'est pas compté dans le suivi." });
    } catch (e) {
      toast.error("Test non envoyé", { description: (e as Error).message });
    } finally {
      setTesting(false);
    }
  };

  const start = async () => {
    setStarting(true);
    try {
      const snapshot = await api.startSend(campaign.id);
      setSummary(null);
      followJob(snapshot);
    } catch (e) {
      toast.error("Envoi impossible", { description: (e as Error).message });
    } finally {
      setStarting(false);
    }
  };

  const control = async (action: "pause" | "resume" | "cancel") => {
    if (!job) return;
    try {
      setJob(await api.controlJob(job.id, action));
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const ready = settings?.email && settings.has_password;
  const body = draft.mode === "text" ? draft.text : draft.html;
  const problems = [
    !ready && { text: "Configure ton compte Gmail", page: "settings" as const },
    !draft.subject.trim() && { text: "Ajoute un objet", page: "message" as const },
    !body.trim() && { text: "Écris le message", page: "message" as const },
    toSend === 0 && { text: "Ajoute des destinataires à qui envoyer", page: "recipients" as const },
  ].filter(Boolean) as { text: string; page: "settings" | "message" | "recipients" }[];

  return (
    <>
      <PageHeader eyebrow={campaign.name} title="Envoi" description="Les mails partent un par un, par une seule connexion Gmail. Le suivi est enregistré après chaque mail." />

      {mine && job && (
        <Card className="mb-6 overflow-hidden">
          <div className="p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  {job.state === "running" && <Spinner size={14} />}
                  <span className="text-sm font-bold">
                    {{ running: "Envoi en cours…", paused: "En pause", done: "Envoi terminé", cancelled: "Envoi annulé", failed: "Envoi interrompu", pending: "Préparation…" }[job.state]}
                  </span>
                </div>
                {job.current && active && <div className="mt-1 font-mono text-xs text-muted">→ {job.current}</div>}
              </div>
              <div className="flex gap-2">
                {job.state === "running" && <Button icon={<Pause size={15} />} onClick={() => control("pause")}>Pause</Button>}
                {job.state === "paused" && <Button variant="primary" icon={<Play size={15} />} onClick={() => control("resume")}>Reprendre</Button>}
                {active && <Button variant="ghost" icon={<Ban size={14} />} onClick={() => control("cancel")}>Annuler</Button>}
              </div>
            </div>
            <div className="mt-5 h-3 overflow-hidden rounded-full bg-surface-2">
              <div
                className={clsx("h-full rounded-full transition-all duration-500", job.state === "failed" ? "bg-bad" : job.state === "paused" ? "bg-warn" : "bg-accent")}
                style={{ width: `${pct}%` }}
              />
            </div>
            <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm tabular-nums">
              <span><strong>{done}</strong> / {job.total}</span>
              <span className="text-ok">✅ {job.sent} envoyé{job.sent > 1 ? "s" : ""}</span>
              <span className={job.errors ? "text-bad" : "text-muted"}>❌ {job.errors} erreur{job.errors > 1 ? "s" : ""}</span>
              {job.skipped > 0 && <span className="text-muted">{job.skipped} ignoré{job.skipped > 1 ? "s" : ""}</span>}
              {active && job.state === "running" && (
                <span className="text-muted">≈ {formatDuration((job.total - done) * (1.5 + (settings?.delay_seconds ?? 0)))} restantes</span>
              )}
            </div>
          </div>
          <div className="max-h-[340px] divide-y divide-line overflow-auto border-t border-line bg-surface-2/40">
            {events.map((e) => <LogLine key={e.seq} e={e} />)}
            <div ref={logEnd} />
          </div>
          {!active && (
            <div className="flex justify-end gap-2 border-t border-line px-6 py-3">
              <Button variant="ghost" onClick={dismissJob}>Masquer</Button>
              <Button variant="soft" onClick={() => { void reloadCampaign(); go("tracking"); }}>Voir le suivi →</Button>
            </div>
          )}
        </Card>
      )}

      {!active && (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <Card className="p-6">
            <h2 className="text-base font-bold">Récapitulatif</h2>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <Stat label="À envoyer" value={toSend} tone="accent" icon={<Rocket size={14} />} />
              <Stat label="Durée estimée" value={<span className="text-xl">{formatDuration(toSend * 1.5 + Math.max(0, toSend - 1) * delay)}</span>} icon={<Clock size={14} />} />
            </div>
            {analysis && (analysis.counts.retry > 0 || analysis.counts.already_sent > 0) && (
              <p className="mt-3 text-xs text-muted">
                Dont {plural(analysis.counts.retry, "adresse")} en erreur retentée{analysis.counts.retry > 1 ? "s" : ""} · {plural(analysis.counts.already_sent, "adresse")} déjà envoyée{analysis.counts.already_sent > 1 ? "s" : ""} ignorée{analysis.counts.already_sent > 1 ? "s" : ""}.
              </p>
            )}
            {toSend > 500 && (
              <div className="mt-4 flex gap-2 rounded-xl bg-warn-soft p-3 text-sm text-warn">
                <AlertTriangle size={17} className="mt-0.5 shrink-0" />
                Plus de 500 destinataires : Gmail bloque généralement au-delà de ~500 mails par jour. Tu peux lancer, puis annuler et reprendre demain : les adresses déjà envoyées seront ignorées.
              </div>
            )}

            <div className="mt-6 space-y-4">
              <Field label="Libellé Gmail (optionnel)" hint="Créé s'il n'existe pas. Utilise / pour un sous-libellé, ex. Scouts/Hikes 2026.">
                <div className="relative">
                  <Tag size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted" />
                  <Input value={draft.label} onChange={(e) => updateDraft({ label: e.target.value })} placeholder="Hikes-2026-2027" className="pl-9" />
                </div>
              </Field>
              <Field label={`Délai entre deux mails : ${delay} s`} hint="Un petit délai rend l'envoi plus naturel pour Gmail.">
                <input
                  type="range"
                  min={0}
                  max={30}
                  step={1}
                  value={delay}
                  onChange={(e) => setDelay(Number(e.target.value))}
                  onMouseUp={() => saveDelay(delay)}
                  onKeyUp={() => saveDelay(delay)}
                  className="w-full accent-[var(--accent)]"
                />
              </Field>
            </div>
          </Card>

          <div className="space-y-4">
            {problems.length > 0 ? (
              <Card className="p-5">
                <h3 className="text-sm font-bold">Avant d'envoyer</h3>
                <ul className="mt-3 space-y-2">
                  {problems.map((p) => (
                    <li key={p.text}>
                      <button onClick={() => go(p.page)} className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-2">
                        <span className="size-2 rounded-full bg-accent" /> {p.text} <span className="ml-auto text-muted">→</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : (
              <Card className="p-5">
                <div className="text-xs font-semibold text-muted">Expéditeur</div>
                <div className="mt-0.5 truncate text-sm font-bold">{settings?.display_name || settings?.email}</div>
                <div className="truncate text-xs text-muted">{settings?.email}</div>
                <div className="mt-3 text-xs font-semibold text-muted">Objet</div>
                <div className="mt-0.5 truncate text-sm">{draft.subject}</div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Badge>{draft.mode === "text" ? "Texte brut" : "HTML + texte"}</Badge>
                  <Badge>{plural(campaign.attachments.length, "pièce jointe", "pièces jointes")}</Badge>
                </div>
              </Card>
            )}
            <Button className="w-full" icon={testing ? <Spinner /> : <FlaskConical size={16} />} disabled={!ready || testing || !draft.subject.trim()} onClick={sendTest}>
              M'envoyer un test
            </Button>
            <Button className="w-full" size="lg" variant="primary" icon={<Rocket size={17} />} disabled={problems.length > 0 || !!otherActive} onClick={openConfirm}>
              Lancer l'envoi
            </Button>
            {otherActive && <p className="text-center text-xs text-muted">Un autre envoi est en cours.</p>}
          </div>
        </div>
      )}

      <Modal
        open={!!summary}
        onClose={() => setSummary(null)}
        title="Confirmer l'envoi"
        footer={
          <>
            <Button variant="ghost" onClick={() => setSummary(null)}>Annuler</Button>
            <Button variant="primary" icon={starting ? <Spinner /> : <Rocket size={16} />} disabled={starting || !summary?.count} onClick={start}>
              Envoyer {summary ? plural(summary.count, "mail") : ""}
            </Button>
          </>
        }
      >
        {summary && (
          <div className="space-y-4 text-sm">
            <div className="rounded-xl bg-accent-soft/60 p-4 text-center">
              <div className="text-4xl font-extrabold tabular-nums text-accent">{summary.count}</div>
              <div className="text-xs font-semibold text-muted">destinataire{summary.count > 1 ? "s" : ""}{summary.retry ? ` dont ${summary.retry} à retenter` : ""}</div>
            </div>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
              <dt className="text-muted">De</dt>
              <dd className="truncate font-semibold">{summary.sender_name ? `${summary.sender_name} <${summary.sender}>` : summary.sender}</dd>
              <dt className="text-muted">Objet</dt>
              <dd className="truncate">{summary.subject}{/\{\w+\}/.test(summary.subject) && <span className="text-muted"> · personnalisé</span>}</dd>
              <dt className="text-muted">Format</dt>
              <dd>{summary.mode === "text" ? "Texte brut" : "HTML (avec version texte)"}</dd>
              <dt className="text-muted">Libellé</dt>
              <dd>{summary.label ? <Badge tone="info"><Tag size={11} /> {summary.label}</Badge> : <span className="text-muted">aucun</span>}</dd>
              <dt className="text-muted">Pièces jointes</dt>
              <dd>{summary.attachments.length ? summary.attachments.map((a) => `${a.name} (${formatBytes(a.size)})`).join(", ") : <span className="text-muted">aucune</span>}</dd>
              <dt className="text-muted">Durée</dt>
              <dd>≈ {formatDuration(summary.estimate_seconds)} <span className="text-muted">({summary.delay_seconds} s entre deux mails)</span></dd>
            </dl>
            {summary.over_limit && (
              <div className="flex gap-2 rounded-xl bg-warn-soft p-3 text-warn">
                <AlertTriangle size={17} className="mt-0.5 shrink-0" />
                Plus de {summary.limit} destinataires : Gmail risque de bloquer l'envoi en cours de route.
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
