import { html as htmlLang } from "@codemirror/lang-html";
import { Prec } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import CodeMirror, { type ReactCodeMirrorRef } from "@uiw/react-codemirror";
import clsx from "clsx";
import { Braces, Code2, Eye, LayoutTemplate, PenTool, Type } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { Attachments } from "../components/Attachments";
import { Button, Card, Input, Modal, PageHeader, Segmented } from "../components/ui";
import { VisualEditor, type VisualEditorHandle } from "../components/VisualEditor";
import { escapeHtml, render, textToHtml, usedVariables } from "../lib/render";
import { TEMPLATES } from "../lib/templates";
import { useAnalysis } from "../lib/useAnalysis";
import { useIsDark } from "../lib/useIsDark";
import { useStore } from "../store";
import type { Mode } from "../types";

const cmTheme = EditorView.theme({
  "&": { backgroundColor: "var(--surface)", color: "var(--ink)" },
  ".cm-gutters": { backgroundColor: "var(--surface)", borderRight: "1px solid var(--line)", color: "var(--muted)" },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--accent) 6%, transparent)" },
  ".cm-activeLineGutter": { backgroundColor: "transparent", color: "var(--ink)" },
});

function previewDoc(body: string, isHtml: boolean, dark: boolean) {
  if (isHtml) {
    // Un document complet garde ses styles ; un fragment reçoit une police de mail par défaut.
    if (/<html[\s>]/i.test(body)) return body;
    return `<!doctype html><html><head><meta charset="utf-8"><style>body{font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:#222;margin:20px;}a{color:#e2552b}</style></head><body>${body}</body></html>`;
  }
  const bg = dark ? "#1f1a17" : "#fff";
  const fg = dark ? "#f3ece4" : "#222";
  return `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:20px;background:${bg};color:${fg};font:14px/1.6 Arial,Helvetica,sans-serif;white-space:pre-wrap;word-wrap:break-word;}</style></head><body>${escapeHtml(body)}</body></html>`;
}

export function MessagePage() {
  const { campaign, updateDraft, settings, go } = useStore();
  const dark = useIsDark();
  const { analysis } = useAnalysis(campaign?.id, campaign?.draft.recipients_raw);
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [confirmVisual, setConfirmVisual] = useState(false);
  const cm = useRef<ReactCodeMirrorRef>(null);
  const visual = useRef<VisualEditorHandle>(null);
  const textArea = useRef<HTMLTextAreaElement>(null);
  const subjectInput = useRef<HTMLInputElement>(null);
  const [focus, setFocus] = useState<"subject" | "body">("body");

  const draft = campaign?.draft;
  const recipients = analysis?.recipients ?? [];
  const previewRecipient = recipients.find((r) => r.email === draft?.preview_email) ?? recipients[0];
  const variables = useMemo(
    () => (previewRecipient ? { ...previewRecipient.fields, email: previewRecipient.email } : {}),
    [previewRecipient],
  );
  const columns = ["email", ...(analysis?.columns ?? [])];

  if (!campaign || !draft) return null;
  const isHtml = draft.mode !== "text";
  const body = isHtml ? draft.html : draft.text;
  const unknown = usedVariables(draft.subject, body).filter((v) => !columns.includes(v));

  const setMode = (mode: Mode) => {
    if (mode === draft.mode) return;
    if (mode === "visual" && draft.mode === "html" && /<(table|style)|style=/i.test(draft.html)) {
      setConfirmVisual(true);
      return;
    }
    const changes: Partial<typeof draft> = { mode };
    if (mode !== "text" && !draft.html.trim() && draft.text.trim()) changes.html = textToHtml(draft.text);
    updateDraft(changes);
  };

  const insertVariable = (name: string) => {
    const token = `{${name}}`;
    if (focus === "subject") {
      const el = subjectInput.current!;
      const start = el.selectionStart ?? draft.subject.length;
      const end = el.selectionEnd ?? start;
      updateDraft({ subject: draft.subject.slice(0, start) + token + draft.subject.slice(end) });
      requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
      return;
    }
    if (draft.mode === "html" && cm.current?.view) {
      const view = cm.current.view;
      const { from, to } = view.state.selection.main;
      view.dispatch({ changes: { from, to, insert: token }, selection: { anchor: from + token.length } });
      view.focus();
    } else if (draft.mode === "visual") {
      visual.current?.insert(token);
    } else if (textArea.current) {
      const el = textArea.current;
      const start = el.selectionStart;
      updateDraft({ text: draft.text.slice(0, start) + token + draft.text.slice(el.selectionEnd) });
      requestAnimationFrame(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
    }
  };

  const applyTemplate = (html: string) => {
    updateDraft({ html, mode: /<(table|style)|style=/i.test(html) ? "html" : draft.mode === "text" ? "html" : draft.mode });
    setTemplatesOpen(false);
  };

  const renderedSubject = render(draft.subject, variables);
  const renderedBody = render(body, variables, isHtml);

  return (
    <>
      <PageHeader
        eyebrow={campaign.name}
        title="Message"
        description="Le brouillon est enregistré automatiquement dans la campagne."
        actions={
          <>
            <Segmented<Mode>
              value={draft.mode}
              onChange={setMode}
              options={[
                { value: "text", label: "Texte", icon: <Type size={14} /> },
                { value: "html", label: "HTML", icon: <Code2 size={14} /> },
                { value: "visual", label: "Visuel", icon: <PenTool size={14} /> },
              ]}
            />
            {isHtml && (
              <Button icon={<LayoutTemplate size={16} />} onClick={() => setTemplatesOpen(true)}>
                Insérer un modèle
              </Button>
            )}
          </>
        }
      />

      <div className="mb-4 grid gap-3">
        <Input
          ref={subjectInput}
          value={draft.subject}
          onFocus={() => setFocus("subject")}
          onChange={(e) => updateDraft({ subject: e.target.value })}
          placeholder="Objet du mail"
          className="h-12 text-base font-semibold"
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mr-1 inline-flex items-center gap-1 text-xs font-semibold text-muted">
            <Braces size={14} /> Insérer {focus === "subject" ? "dans l'objet" : "dans le message"} :
          </span>
          {columns.map((c) => (
            <button
              key={c}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => insertVariable(c)}
              className="rounded-md border border-line bg-surface px-2 py-0.5 font-mono text-xs hover:border-accent hover:text-accent"
            >
              {`{${c}}`}
            </button>
          ))}
          {columns.length === 1 && (
            <span className="text-xs text-muted">— colle un tableau Excel dans Destinataires pour avoir {"{prenom}"}, {"{nom}"}…</span>
          )}
        </div>
        {unknown.length > 0 && (
          <div className="rounded-xl bg-warn-soft px-3 py-2 text-xs text-warn">
            Variable{unknown.length > 1 ? "s" : ""} sans colonne correspondante : {unknown.map((u) => `{${u}}`).join(", ")}. Elle{unknown.length > 1 ? "s" : ""} sera{unknown.length > 1 ? "ont" : ""} envoyée{unknown.length > 1 ? "s" : ""} telle{unknown.length > 1 ? "s" : ""} quelle{unknown.length > 1 ? "s" : ""}.
          </div>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="h-[560px] overflow-hidden" >
          <div onFocus={() => setFocus("body")} className="h-full">
            {draft.mode === "text" && (
              <textarea
                ref={textArea}
                value={draft.text}
                onChange={(e) => updateDraft({ text: e.target.value })}
                placeholder={"Bonjour {prenom},\n\n…"}
                className="h-full w-full resize-none bg-transparent p-5 text-[14px] leading-relaxed outline-none placeholder:text-muted/70"
              />
            )}
            {draft.mode === "html" && (
              <CodeMirror
                ref={cm}
                value={draft.html}
                height="560px"
                theme={dark ? "dark" : "light"}
                extensions={[htmlLang(), EditorView.lineWrapping, Prec.highest(cmTheme)]}
                onChange={(value) => updateDraft({ html: value })}
                basicSetup={{ foldGutter: true, highlightActiveLine: true }}
                placeholder="<p>Bonjour {prenom},</p>"
              />
            )}
            {draft.mode === "visual" && (
              <VisualEditor ref={visual} html={draft.html} onChange={(html) => updateDraft({ html })} />
            )}
          </div>
        </Card>

        <Card className="flex h-[560px] flex-col overflow-hidden">
          <div className="space-y-1.5 border-b border-line px-5 py-3 text-[13px]">
            <div className="flex items-center justify-between gap-3">
              <span className="inline-flex items-center gap-1.5 text-xs font-bold tracking-[.12em] text-muted uppercase">
                <Eye size={14} /> Aperçu
              </span>
              {recipients.length > 0 && (
                <select
                  value={previewRecipient?.email}
                  onChange={(e) => updateDraft({ preview_email: e.target.value })}
                  className="max-w-[60%] truncate rounded-lg border border-line bg-surface px-2 py-1 text-xs"
                >
                  {recipients.slice(0, 500).map((r) => (
                    <option key={r.email} value={r.email}>
                      {r.fields.prenom || r.fields.nom ? `${r.fields.prenom ?? ""} ${r.fields.nom ?? ""}`.trim() + ` — ${r.email}` : r.email}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="truncate"><span className="text-muted">De :</span> {settings?.display_name ? `${settings.display_name} <${settings.email}>` : settings?.email || "—"}</div>
            <div className="truncate"><span className="text-muted">À :</span> {previewRecipient?.email ?? "—"}</div>
            <div className="truncate font-bold">{renderedSubject || <span className="font-normal text-muted">(sans objet)</span>}</div>
          </div>
          <iframe
            title="Aperçu du message"
            sandbox=""
            srcDoc={previewDoc(renderedBody, isHtml, dark)}
            className={clsx("min-h-0 w-full flex-1", isHtml ? "bg-white" : "bg-surface")}
          />
        </Card>
      </div>

      <div className="mt-4">
        <Attachments />
      </div>

      <div className="mt-6 flex justify-end">
        <Button variant="primary" onClick={() => go("send")} disabled={!draft.subject.trim() || !body.trim()}>
          Préparer l'envoi →
        </Button>
      </div>

      <Modal open={templatesOpen} onClose={() => setTemplatesOpen(false)} title="Insérer un modèle" width="max-w-3xl">
        <p className="mb-4 text-sm text-muted">Le modèle remplace le contenu actuel du message.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          {TEMPLATES.map((t) => (
            <button key={t.id} onClick={() => applyTemplate(t.html)} className="group overflow-hidden rounded-xl border border-line text-left transition hover:border-accent">
              <div className="h-40 overflow-hidden bg-white">
                <iframe title={t.name} sandbox="" srcDoc={previewDoc(t.html, true, false)} className="pointer-events-none h-[400px] w-[250%] origin-top-left scale-[.4]" />
              </div>
              <div className="border-t border-line p-3">
                <div className="text-sm font-bold group-hover:text-accent">{t.name}</div>
                <div className="mt-0.5 text-xs text-muted">{t.description}</div>
              </div>
            </button>
          ))}
        </div>
      </Modal>

      <Modal
        open={confirmVisual}
        onClose={() => setConfirmVisual(false)}
        title="Passer en mode visuel ?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmVisual(false)}>Rester en HTML</Button>
            <Button variant="primary" onClick={() => { setConfirmVisual(false); updateDraft({ mode: "visual" }); }}>Passer en visuel</Button>
          </>
        }
      >
        <p className="text-sm">Ce HTML contient des tableaux ou des styles que l'éditeur visuel ne sait pas garder : la mise en page sera simplifiée dès que tu modifieras le texte.</p>
      </Modal>
    </>
  );
}
