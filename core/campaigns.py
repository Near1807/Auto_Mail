"""Campagnes : un dossier par campagne dans ``campagnes/``.

::

    campagnes/<id>/
        suivi.csv       le CSV de suivi
        message.json    le brouillon mémorisé (objet, corps, destinataires, libellé…)
        pj/             les pièces jointes
"""

from __future__ import annotations

import json
import os
import re
import shutil
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import tracking as tracking_mod
from .message import Draft

CSV_NAME = "suivi.csv"
DRAFT_NAME = "message.json"
ATTACHMENTS_DIR = "pj"


@dataclass
class StoredDraft:
    name: str = ""
    created: str = ""
    subject: str = ""
    mode: str = "text"  # text | html | visual
    text: str = ""
    html: str = ""
    recipients_raw: str = ""
    label: str = ""
    preview_email: str = ""
    updated: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "StoredDraft":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:60] or "campagne"


@dataclass
class Campaign:
    id: str
    path: Path
    draft: StoredDraft = field(default_factory=StoredDraft)

    @property
    def csv_path(self) -> Path:
        return self.path / CSV_NAME

    @property
    def attachments_dir(self) -> Path:
        return self.path / ATTACHMENTS_DIR

    def attachments(self) -> list[Path]:
        if not self.attachments_dir.exists():
            return []
        return sorted(p for p in self.attachments_dir.iterdir() if p.is_file() and not p.name.startswith("."))

    def to_draft(self) -> Draft:
        d = self.draft
        return Draft(subject=d.subject, mode=d.mode, text=d.text, html=d.html, attachments=self.attachments())

    def summary(self) -> dict:
        counts = tracking_mod.load(self.csv_path).counts() if self.csv_path.exists() else {
            "total": 0, "sent": 0, "errors": 0, "replies": 0}
        return {
            "id": self.id,
            "name": self.draft.name or self.id,
            "created": self.draft.created,
            "updated": self.draft.updated,
            "subject": self.draft.subject,
            "counts": counts,
        }


class CampaignStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _load(self, path: Path) -> Campaign:
        draft_file = path / DRAFT_NAME
        draft = StoredDraft(name=path.name)
        if draft_file.exists():
            try:
                draft = StoredDraft.from_dict(json.loads(draft_file.read_text(encoding="utf-8")))
            except (ValueError, TypeError):
                pass
        return Campaign(id=path.name, path=path, draft=draft)

    def list(self) -> list[Campaign]:
        campaigns = [self._load(p) for p in self.root.iterdir() if p.is_dir() and not p.name.startswith(".")]
        return sorted(campaigns, key=lambda c: c.draft.updated or c.draft.created, reverse=True)

    def get(self, campaign_id: str) -> Campaign:
        if not re.fullmatch(r"[a-z0-9-]+", campaign_id or ""):
            raise KeyError(campaign_id)
        path = self.root / campaign_id
        if not path.is_dir():
            raise KeyError(campaign_id)
        return self._load(path)

    def _unique_id(self, name: str, exclude: str | None = None) -> str:
        base = slugify(name)
        candidate, n = base, 2
        while (self.root / candidate).exists() and candidate != exclude:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def create(self, name: str) -> Campaign:
        name = name.strip() or "Nouvelle campagne"
        campaign_id = self._unique_id(name)
        path = self.root / campaign_id
        path.mkdir(parents=True)
        now = datetime.now().isoformat(timespec="seconds")
        campaign = Campaign(id=campaign_id, path=path, draft=StoredDraft(name=name, created=now, updated=now, label=name))
        self.save_draft(campaign)
        return campaign

    def save_draft(self, campaign: Campaign) -> None:
        campaign.draft.updated = datetime.now().isoformat(timespec="seconds")
        target = campaign.path / DRAFT_NAME
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(campaign.draft), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)

    def update_draft(self, campaign_id: str, changes: dict) -> Campaign:
        campaign = self.get(campaign_id)
        for key, value in changes.items():
            if key in StoredDraft.__dataclass_fields__ and key not in ("name", "created", "updated"):
                setattr(campaign.draft, key, value)
        self.save_draft(campaign)
        return campaign

    def rename(self, campaign_id: str, new_name: str) -> Campaign:
        campaign = self.get(campaign_id)
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Le nom ne peut pas être vide.")
        new_id = self._unique_id(new_name, exclude=campaign_id)
        if new_id != campaign_id:
            campaign.path.rename(self.root / new_id)
            campaign = self.get(new_id)
        campaign.draft.name = new_name
        self.save_draft(campaign)
        return campaign

    def delete(self, campaign_id: str) -> None:
        shutil.rmtree(self.get(campaign_id).path)

    def import_csv(self, name: str, content: bytes) -> Campaign:
        """Crée une campagne à partir d'un ancien CSV, réécrit au format actuel."""
        tracking = tracking_mod.parse_csv_text(tracking_mod.decode_bytes(content))
        campaign = self.create(name)
        try:
            tracking_mod.save(tracking, campaign.csv_path)
        except Exception:
            shutil.rmtree(campaign.path, ignore_errors=True)
            raise
        return campaign

    def add_attachment(self, campaign_id: str, filename: str, content: bytes) -> Path:
        campaign = self.get(campaign_id)
        campaign.attachments_dir.mkdir(exist_ok=True)
        safe = Path(filename).name.strip().replace("\x00", "") or "piece-jointe"
        target = campaign.attachments_dir / safe
        stem, suffix, n = target.stem, target.suffix, 2
        while target.exists():
            target = campaign.attachments_dir / f"{stem} ({n}){suffix}"
            n += 1
        target.write_bytes(content)
        return target

    def remove_attachment(self, campaign_id: str, filename: str) -> None:
        campaign = self.get(campaign_id)
        target = campaign.attachments_dir / Path(filename).name
        if target.parent == campaign.attachments_dir and target.is_file():
            target.unlink()
