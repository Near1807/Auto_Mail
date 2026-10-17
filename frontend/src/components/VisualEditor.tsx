import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { EditorContent, useEditor, type Editor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import clsx from "clsx";
import {
  AlignCenter,
  AlignLeft,
  Bold,
  Heading1,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  Quote,
  Redo2,
  Underline as UnderlineIcon,
  Undo2,
} from "lucide-react";
import { useEffect, useImperativeHandle, forwardRef, type ReactNode } from "react";

export type VisualEditorHandle = { insert: (text: string) => void };

function Tool({ on, active, title, children }: { on: () => void; active?: boolean; title: string; children: ReactNode }) {
  return (
    <button
      type="button"
      title={title}
      onMouseDown={(e) => e.preventDefault()}
      onClick={on}
      className={clsx("grid size-8 place-items-center rounded-lg transition", active ? "bg-accent-soft text-accent" : "text-muted hover:bg-surface-2 hover:text-ink")}
    >
      {children}
    </button>
  );
}

function Toolbar({ editor }: { editor: Editor }) {
  const link = () => {
    const previous = editor.getAttributes("link").href as string | undefined;
    const url = window.prompt("Adresse du lien (vide pour retirer)", previous ?? "https://");
    if (url === null) return;
    if (!url) editor.chain().focus().unsetLink().run();
    else editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
  };
  const sep = <span className="mx-1 h-5 w-px bg-line" />;
  return (
    <div className="flex flex-wrap items-center gap-0.5 border-b border-line px-2 py-1.5">
      <Tool title="Gras" on={() => editor.chain().focus().toggleBold().run()} active={editor.isActive("bold")}><Bold size={15} /></Tool>
      <Tool title="Italique" on={() => editor.chain().focus().toggleItalic().run()} active={editor.isActive("italic")}><Italic size={15} /></Tool>
      <Tool title="Souligné" on={() => editor.chain().focus().toggleUnderline().run()} active={editor.isActive("underline")}><UnderlineIcon size={15} /></Tool>
      <Tool title="Lien" on={link} active={editor.isActive("link")}><Link2 size={15} /></Tool>
      {sep}
      <Tool title="Titre" on={() => editor.chain().focus().toggleHeading({ level: 1 }).run()} active={editor.isActive("heading", { level: 1 })}><Heading1 size={15} /></Tool>
      <Tool title="Sous-titre" on={() => editor.chain().focus().toggleHeading({ level: 2 }).run()} active={editor.isActive("heading", { level: 2 })}><Heading2 size={15} /></Tool>
      <Tool title="Liste à puces" on={() => editor.chain().focus().toggleBulletList().run()} active={editor.isActive("bulletList")}><List size={15} /></Tool>
      <Tool title="Liste numérotée" on={() => editor.chain().focus().toggleOrderedList().run()} active={editor.isActive("orderedList")}><ListOrdered size={15} /></Tool>
      <Tool title="Citation" on={() => editor.chain().focus().toggleBlockquote().run()} active={editor.isActive("blockquote")}><Quote size={15} /></Tool>
      {sep}
      <Tool title="Aligner à gauche" on={() => editor.chain().focus().setTextAlign("left").run()} active={editor.isActive({ textAlign: "left" })}><AlignLeft size={15} /></Tool>
      <Tool title="Centrer" on={() => editor.chain().focus().setTextAlign("center").run()} active={editor.isActive({ textAlign: "center" })}><AlignCenter size={15} /></Tool>
      {sep}
      <Tool title="Annuler" on={() => editor.chain().focus().undo().run()}><Undo2 size={15} /></Tool>
      <Tool title="Rétablir" on={() => editor.chain().focus().redo().run()}><Redo2 size={15} /></Tool>
    </div>
  );
}

export const VisualEditor = forwardRef<VisualEditorHandle, { html: string; onChange: (html: string) => void }>(
  function VisualEditor({ html, onChange }, ref) {
    const editor = useEditor({
      extensions: [
        StarterKit,
        Underline,
        Link.configure({ openOnClick: false, autolink: true }),
        TextAlign.configure({ types: ["heading", "paragraph"] }),
        Placeholder.configure({ placeholder: "Écris ton message… Les variables comme {prenom} fonctionnent ici aussi." }),
      ],
      content: html,
      editorProps: { attributes: { class: "prose-mail px-5 py-4" } },
      onUpdate: ({ editor }) => onChange(editor.isEmpty ? "" : editor.getHTML()),
    });

    useEffect(() => {
      // Contenu remplacé de l'extérieur (modèle inséré, changement de campagne).
      if (editor && html !== editor.getHTML() && !editor.isFocused) editor.commands.setContent(html, false);
    }, [html, editor]);

    useImperativeHandle(ref, () => ({ insert: (text) => editor?.chain().focus().insertContent(text).run() }), [editor]);

    if (!editor) return null;
    return (
      <div className="flex h-full flex-col">
        <Toolbar editor={editor} />
        <div className="min-h-0 flex-1 overflow-auto" onClick={() => editor.chain().focus().run()}>
          <EditorContent editor={editor} />
        </div>
      </div>
    );
  },
);
