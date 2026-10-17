import clsx from "clsx";
import { FolderOpen, Monitor, Moon, PenLine, Send, Settings as Cog, Sun, Table2, Users } from "lucide-react";
import type { ReactNode } from "react";
import { useStore, type Page } from "../store";

const NAV: { page: Page; label: string; icon: ReactNode; needsCampaign?: boolean }[] = [
  { page: "campaigns", label: "Campagnes", icon: <FolderOpen size={18} /> },
  { page: "recipients", label: "Destinataires", icon: <Users size={18} />, needsCampaign: true },
  { page: "message", label: "Message", icon: <PenLine size={18} />, needsCampaign: true },
  { page: "send", label: "Envoi", icon: <Send size={18} />, needsCampaign: true },
  { page: "tracking", label: "Suivi", icon: <Table2 size={18} />, needsCampaign: true },
];

export function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid size-10 -rotate-6 place-items-center rounded-xl bg-accent text-accent-ink shadow-[0_6px_14px_-6px_var(--accent)]">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="5.5" width="18" height="13" rx="2.5" />
          <path d="m3.8 7 8.2 6 8.2-6" />
        </svg>
      </div>
      <div className="leading-tight">
        <div className="text-[15px] font-extrabold tracking-tight">Auto Mail</div>
        <div className="text-[11px] font-medium text-muted">envois Gmail en série</div>
      </div>
    </div>
  );
}

export function Sidebar() {
  const { page, go, campaign, job, settings, theme, setTheme } = useStore();
  const running = job && (job.state === "running" || job.state === "paused");
  const pct = job && job.total ? Math.round(((job.sent + job.errors + job.skipped) / job.total) * 100) : 0;

  const item = (p: Page, label: string, icon: ReactNode, disabled = false, extra?: ReactNode) => (
    <button
      key={p}
      disabled={disabled}
      onClick={() => go(p)}
      className={clsx(
        "group relative flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-semibold transition",
        page === p ? "bg-surface text-ink shadow-sm ring-1 ring-line" : "text-muted hover:bg-surface/60 hover:text-ink",
        disabled && "pointer-events-none opacity-40",
      )}
    >
      <span className={clsx("transition", page === p ? "text-accent" : "")}>{icon}</span>
      <span className="flex-1 text-left">{label}</span>
      {extra}
    </button>
  );

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-surface-2/60 px-3 pt-5 pb-3">
      <div className="px-2">
        <Logo />
      </div>

      <div className="mx-1 mt-6 mb-2 rounded-xl border border-dashed border-line px-3 py-2.5">
        <div className="text-[10px] font-bold tracking-[.14em] text-muted uppercase">Campagne</div>
        {campaign ? (
          <button onClick={() => go("campaigns")} className="mt-0.5 block w-full truncate text-left text-sm font-bold hover:text-accent" title={campaign.name}>
            {campaign.name}
          </button>
        ) : (
          <button onClick={() => go("campaigns")} className="mt-0.5 text-sm font-semibold text-accent">
            Choisir une campagne →
          </button>
        )}
      </div>

      <nav className="mt-2 space-y-1">
        {NAV.map((n) =>
          item(
            n.page,
            n.label,
            n.icon,
            n.needsCampaign && !campaign,
            n.page === "send" && running ? (
              <span className="rounded-full bg-accent px-1.5 py-0.5 text-[10px] font-bold text-accent-ink tabular-nums">{pct}%</span>
            ) : undefined,
          ),
        )}
      </nav>

      {running && (
        <button onClick={() => go("send")} className="mx-1 mt-4 rounded-xl bg-surface p-3 text-left ring-1 ring-line">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span>{job.state === "paused" ? "En pause" : "Envoi en cours"}</span>
            <span className="tabular-nums text-muted">
              {job.sent + job.errors + job.skipped}/{job.total}
            </span>
          </div>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-2">
            <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
          </div>
        </button>
      )}

      <div className="mt-auto space-y-2">
        {item(
          "settings",
          "Réglages",
          <Cog size={18} />,
          false,
          settings && !settings.has_password ? <span className="size-2 rounded-full bg-accent" title="Compte à configurer" /> : undefined,
        )}
        <div className="flex items-center justify-between rounded-xl px-3 py-1">
          <span className="truncate text-[11px] text-muted" title={settings?.email}>
            {settings?.email || "Aucun compte"}
          </span>
          <div className="flex rounded-lg bg-surface p-0.5 ring-1 ring-line">
            {(
              [
                ["light", <Sun size={13} />, "Clair"],
                ["system", <Monitor size={13} />, "Système"],
                ["dark", <Moon size={13} />, "Sombre"],
              ] as const
            ).map(([t, icon, label]) => (
              <button
                key={t}
                title={label}
                onClick={() => setTheme(t)}
                className={clsx("grid size-6 place-items-center rounded-md", theme === t ? "bg-accent-soft text-accent" : "text-muted hover:text-ink")}
              >
                {icon}
              </button>
            ))}
          </div>
        </div>
      </div>
    </aside>
  );
}
