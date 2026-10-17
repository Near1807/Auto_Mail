import clsx from "clsx";
import { FileText, Paperclip, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "../api";
import { formatBytes } from "../lib/render";
import { useStore } from "../store";

export function Attachments() {
  const { campaign, setCampaign } = useStore();
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  if (!campaign) return null;

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    try {
      const attachments = await api.addAttachments(campaign.id, files);
      setCampaign({ ...campaign, attachments });
      toast.success(files.length > 1 ? `${files.length} pièces jointes ajoutées` : `« ${files[0].name} » ajoutée`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (name: string) => {
    const attachments = await api.removeAttachment(campaign.id, name);
    setCampaign({ ...campaign, attachments });
  };

  const total = campaign.attachments.reduce((s, a) => s + a.size, 0);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        void upload([...e.dataTransfer.files]);
      }}
      className={clsx("rounded-2xl border-2 border-dashed p-3 transition", over ? "border-accent bg-accent-soft/40" : "border-line")}
    >
      <input ref={input} type="file" multiple hidden onChange={(e) => { void upload([...(e.target.files ?? [])]); e.target.value = ""; }} />
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-1 text-[13px] font-semibold text-muted">
          <Paperclip size={15} /> Pièces jointes
        </span>
        {campaign.attachments.map((a) => (
          <span key={a.name} className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface py-1 pr-1 pl-2 text-xs">
            <FileText size={14} className="text-accent" />
            <span className="max-w-[220px] truncate font-semibold">{a.name}</span>
            <span className="text-muted">{formatBytes(a.size)}</span>
            <button onClick={() => remove(a.name)} className="rounded-md p-0.5 text-muted hover:bg-bad-soft hover:text-bad" aria-label={`Retirer ${a.name}`}>
              <X size={13} />
            </button>
          </span>
        ))}
        <button
          onClick={() => input.current?.click()}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-semibold text-accent hover:bg-accent-soft"
        >
          <Upload size={13} /> {campaign.attachments.length ? "Ajouter" : "Glisse des fichiers ici ou clique"}
        </button>
        {total > 20 * 1024 * 1024 && <span className="text-xs font-semibold text-bad">Plus de 20 Mo : Gmail risque de refuser (limite 25 Mo).</span>}
      </div>
    </div>
  );
}
