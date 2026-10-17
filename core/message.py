"""Construction des mails : variables, texte brut depuis le HTML, multipart, pièces jointes."""

from __future__ import annotations

import html
import mimetypes
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html.parser import HTMLParser
from pathlib import Path
from typing import Mapping

VARIABLE_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class Draft:
    subject: str = ""
    mode: str = "text"  # "text" | "html" (le mode visuel produit du HTML)
    text: str = ""
    html: str = ""
    attachments: list[Path] = field(default_factory=list)

    @property
    def is_html(self) -> bool:
        return self.mode in ("html", "visual")


def render(template: str, variables: Mapping[str, str], escape: bool = False) -> str:
    """Remplace ``{nom}`` par sa valeur ; une variable inconnue reste telle quelle."""

    def replace(match: re.Match) -> str:
        key = match.group(1).lower()
        if key not in variables:
            return match.group(0)
        value = variables[key] or ""
        return html.escape(value) if escape else value

    return VARIABLE_RE.sub(replace, template)


def used_variables(*templates: str) -> set[str]:
    return {m.lower() for t in templates for m in VARIABLE_RE.findall(t or "")}


class _TextExtractor(HTMLParser):
    BLOCKS = {"p", "div", "section", "article", "header", "footer", "table", "tr", "h1", "h2",
              "h3", "h4", "h5", "h6", "ul", "ol", "blockquote", "hr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.links: list[str | None] = []
        self.skip = 0
        self.list_stack: list[list[int]] = []  # [est_ordonnée, compteur]

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("style", "script", "head", "title"):
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag in ("ul", "ol"):
            self.list_stack.append([tag == "ol", 0])
            self.parts.append("\n")
        elif tag == "li":
            prefix = "- "
            if self.list_stack and self.list_stack[-1][0]:
                self.list_stack[-1][1] += 1
                prefix = f"{self.list_stack[-1][1]}. "
            self.parts.append("\n" + "  " * max(0, len(self.list_stack) - 1) + prefix)
        elif tag in ("td", "th"):
            self.parts.append("\t")
        elif tag == "a":
            self.links.append(attrs.get("href"))
            self.parts.append("")
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "title"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            self.parts.append("\n")
        elif tag == "a":
            href = self.links.pop() if self.links else None
            if href and not href.startswith(("#", "javascript:")):
                target = href[7:] if href.startswith("mailto:") else href
                text = self.parts[-1] if self.parts else ""
                if target not in text:
                    self.parts.append(f" ({target})")
        elif tag in self.BLOCKS:
            self.parts.append("\n\n")

    def handle_data(self, data):
        if self.skip:
            return
        self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(source: str) -> str:
    parser = _TextExtractor()
    parser.feed(source or "")
    parser.close()
    text = "".join(parser.parts)
    lines = [line.strip(" ") for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def recipient_variables(email: str, fields: Mapping[str, str]) -> dict[str, str]:
    variables = {k.lower(): v for k, v in fields.items()}
    variables["email"] = email
    return variables


def build_message(
    draft: Draft,
    sender_email: str,
    sender_name: str,
    to: str,
    variables: Mapping[str, str] | None = None,
) -> EmailMessage:
    variables = variables or {}
    domain = sender_email.split("@")[-1] if "@" in sender_email else None
    msg = EmailMessage()
    msg["Subject"] = render(draft.subject, variables)
    msg["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    msg["To"] = to
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=domain)
    if draft.is_html:
        body = render(draft.html, variables, escape=True)
        msg.set_content(html_to_text(body))
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(render(draft.text, variables))
    for path in draft.attachments:
        ctype, encoding = mimetypes.guess_type(path.name)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    return msg
