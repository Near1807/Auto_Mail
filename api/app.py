"""API HTTP d'Auto Mail (FastAPI) + service du front compilé.

Tout est local : le serveur n'écoute que sur 127.0.0.1. ``create_app`` accepte des
fabriques SMTP/IMAP et un magasin de mots de passe pour que les tests n'utilisent
ni le réseau ni le vrai Gestionnaire d'identification.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import paths
from core import tracking as tracking_mod
from core.addresses import parse_recipients
from core.campaigns import Campaign, CampaignStore
from core.gmail import AuthError, ImapSession, check_connection, default_imap_factory, default_smtp_factory, friendly_error
from core.sender import GMAIL_DAILY_LIMIT, Job, SendConfig, estimate_seconds, send_test
from core.settings import PasswordStore, Settings, load_settings, save_settings


class SettingsIn(BaseModel):
    email: Optional[str] = None
    display_name: Optional[str] = None
    delay_seconds: Optional[float] = None
    theme: Optional[str] = None


class PasswordIn(BaseModel):
    password: str


class ConnectionTestIn(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None


class NameIn(BaseModel):
    name: str


class DraftIn(BaseModel):
    subject: Optional[str] = None
    mode: Optional[str] = None
    text: Optional[str] = None
    html: Optional[str] = None
    recipients_raw: Optional[str] = None
    label: Optional[str] = None
    preview_email: Optional[str] = None


class AnalyzeIn(BaseModel):
    raw: Optional[str] = None


class CellIn(BaseModel):
    email: str
    column: str = "reponse"
    value: str


def static_dir() -> Optional[Path]:
    candidates = []
    if os.environ.get("AUTOMAIL_STATIC"):
        candidates.append(Path(os.environ["AUTOMAIL_STATIC"]))
    if getattr(sys, "_MEIPASS", None):
        candidates.append(Path(sys._MEIPASS) / "frontend_dist")
    candidates.append(Path(__file__).resolve().parents[1] / "frontend" / "dist")
    return next((c for c in candidates if (c / "index.html").exists()), None)


def open_in_explorer(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def create_app(
    smtp_factory: Callable = default_smtp_factory,
    imap_factory: Callable = default_imap_factory,
    passwords: Optional[PasswordStore] = None,
    opener: Callable[[Path], None] = open_in_explorer,
    serve_static: bool = True,
) -> FastAPI:
    app = FastAPI(title="Auto Mail", docs_url="/api/docs", openapi_url="/api/openapi.json")
    store = CampaignStore(paths.campaigns_dir())
    password_store = passwords or PasswordStore()
    jobs: dict[str, Job] = {}

    def settings() -> Settings:
        return load_settings(paths.settings_file())

    def campaign_or_404(campaign_id: str) -> Campaign:
        try:
            return store.get(campaign_id)
        except KeyError:
            raise HTTPException(404, "Campagne introuvable.")

    def active_job() -> Optional[Job]:
        return next((j for j in jobs.values() if not j.finished), None)

    def ensure_not_sending(campaign_id: str) -> None:
        job = active_job()
        if job and job.config.campaign_id == campaign_id:
            raise HTTPException(409, "Un envoi est en cours sur cette campagne : attends qu'il se termine.")

    def credentials() -> tuple[Settings, str]:
        s = settings()
        if not s.email:
            raise HTTPException(400, "Renseigne d'abord ton adresse Gmail dans les Réglages.")
        password = password_store.get(s.email)
        if not password:
            raise HTTPException(400, "Aucun mot de passe d'application enregistré : va dans les Réglages.")
        return s, password

    def analyze(campaign: Campaign, raw: str) -> dict:
        parsed = parse_recipients(raw)
        tracking = tracking_mod.load(campaign.csv_path)
        classes = tracking_mod.classify(parsed.recipients, tracking)
        status = {}
        for r in classes.already_sent:
            status[r.email] = "sent"
        for r in classes.retry:
            status[r.email] = "retry"
        for r in classes.new:
            status[r.email] = "new"
        return {
            "recipients": [{"email": r.email, "fields": r.fields, "status": status[r.email]} for r in parsed.recipients],
            "invalid": parsed.invalid,
            "duplicates": parsed.duplicates,
            "columns": parsed.columns,
            "counts": {
                "valid": len(parsed.recipients),
                "invalid": len(parsed.invalid),
                "duplicates": len(parsed.duplicates),
                "already_sent": len(classes.already_sent),
                "retry": len(classes.retry),
                "new": len(classes.new),
                "to_send": len(classes.to_send),
            },
        }, classes

    def attachments_info(campaign: Campaign) -> list[dict]:
        return [{"name": p.name, "size": p.stat().st_size} for p in campaign.attachments()]

    def campaign_detail(campaign: Campaign) -> dict:
        data = campaign.summary()
        data["draft"] = campaign.draft.__dict__
        data["attachments"] = attachments_info(campaign)
        data["path"] = str(campaign.path)
        return data

    @app.exception_handler(tracking_mod.CsvLockedError)
    async def locked_handler(request: Request, error: tracking_mod.CsvLockedError):
        return JSONResponse({"detail": str(error)}, status_code=423)

    # ------------------------------------------------------------------ réglages
    @app.get("/api/settings")
    def get_settings():
        s = settings()
        return {**s.__dict__, "has_password": bool(password_store.get(s.email)),
                "data_dir": str(paths.data_dir())}

    @app.put("/api/settings")
    def put_settings(body: SettingsIn):
        s = settings()
        old_email = s.email
        for key, value in body.model_dump(exclude_none=True).items():
            setattr(s, key, value.strip() if isinstance(value, str) else value)
        if s.theme not in ("system", "light", "dark"):
            s.theme = "system"
        s.delay_seconds = max(0.0, min(float(s.delay_seconds), 600.0))
        if old_email and s.email.lower() != old_email.lower():
            # Le mot de passe suit l'adresse : on le déplace pour ne pas le perdre.
            previous = password_store.get(old_email)
            if previous and s.email:
                password_store.set(s.email, previous)
                password_store.delete(old_email)
        save_settings(s, paths.settings_file())
        return get_settings()

    @app.put("/api/account/password")
    def put_password(body: PasswordIn):
        s = settings()
        if not s.email:
            raise HTTPException(400, "Renseigne d'abord ton adresse Gmail.")
        if body.password.strip():
            password_store.set(s.email, body.password.strip())
        else:
            password_store.delete(s.email)
        return get_settings()

    @app.post("/api/account/test")
    def test_account(body: ConnectionTestIn):
        s = settings()
        email = (body.email or s.email).strip()
        password = (body.password or "").replace(" ", "") or password_store.get(email)
        if not email or not password:
            raise HTTPException(400, "Adresse et mot de passe d'application requis.")
        try:
            check_connection(email, password, smtp_factory=smtp_factory, imap_factory=imap_factory)
        except Exception as error:
            return {"ok": False, "message": friendly_error(error)}
        return {"ok": True, "message": "Connexion réussie à Gmail (envoi et libellés)."}

    # ----------------------------------------------------------------- campagnes
    @app.get("/api/campaigns")
    def list_campaigns():
        return [c.summary() for c in store.list()]

    @app.post("/api/campaigns", status_code=201)
    def create_campaign(body: NameIn):
        return campaign_detail(store.create(body.name))

    @app.post("/api/campaigns/import", status_code=201)
    async def import_campaign(file: UploadFile = File(...), name: str = Form("")):
        content = await file.read()
        title = name.strip() or Path(file.filename or "Import").stem.replace("_", " ")
        try:
            return campaign_detail(store.import_csv(title, content))
        except ValueError as error:
            raise HTTPException(400, str(error))

    @app.get("/api/campaigns/{campaign_id}")
    def get_campaign(campaign_id: str):
        return campaign_detail(campaign_or_404(campaign_id))

    @app.patch("/api/campaigns/{campaign_id}")
    def rename_campaign(campaign_id: str, body: NameIn):
        campaign_or_404(campaign_id)
        ensure_not_sending(campaign_id)
        try:
            return campaign_detail(store.rename(campaign_id, body.name))
        except ValueError as error:
            raise HTTPException(400, str(error))

    @app.delete("/api/campaigns/{campaign_id}", status_code=204)
    def delete_campaign(campaign_id: str):
        campaign_or_404(campaign_id)
        ensure_not_sending(campaign_id)
        store.delete(campaign_id)
        return Response(status_code=204)

    @app.put("/api/campaigns/{campaign_id}/draft")
    def put_draft(campaign_id: str, body: DraftIn):
        campaign_or_404(campaign_id)
        changes = body.model_dump(exclude_none=True)
        if "mode" in changes and changes["mode"] not in ("text", "html", "visual"):
            raise HTTPException(400, "Mode inconnu.")
        return campaign_detail(store.update_draft(campaign_id, changes))

    @app.post("/api/campaigns/{campaign_id}/attachments", status_code=201)
    async def add_attachments(campaign_id: str, files: list[UploadFile] = File(...)):
        campaign_or_404(campaign_id)
        for upload in files:
            store.add_attachment(campaign_id, upload.filename or "piece-jointe", await upload.read())
        return attachments_info(store.get(campaign_id))

    @app.delete("/api/campaigns/{campaign_id}/attachments/{name}")
    def remove_attachment(campaign_id: str, name: str):
        campaign_or_404(campaign_id)
        store.remove_attachment(campaign_id, name)
        return attachments_info(store.get(campaign_id))

    @app.post("/api/campaigns/{campaign_id}/open-folder")
    def open_folder(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        opener(campaign.path)
        return {"ok": True}

    # ------------------------------------------------------------ destinataires
    @app.post("/api/campaigns/{campaign_id}/analyze")
    def analyze_recipients(campaign_id: str, body: AnalyzeIn):
        campaign = campaign_or_404(campaign_id)
        raw = body.raw if body.raw is not None else campaign.draft.recipients_raw
        return analyze(campaign, raw)[0]

    # ---------------------------------------------------------------------- envoi
    def build_config(campaign: Campaign, password: str, s: Settings, recipients) -> SendConfig:
        return SendConfig(
            sender_email=s.email, sender_name=s.display_name, password=password,
            draft=campaign.to_draft(), recipients=recipients, csv_path=campaign.csv_path,
            label=campaign.draft.label.strip(), delay_seconds=s.delay_seconds, campaign_id=campaign.id,
        )

    def check_draft(campaign: Campaign) -> None:
        d = campaign.draft
        if not d.subject.strip():
            raise HTTPException(400, "L'objet du message est vide.")
        body = d.html if d.mode in ("html", "visual") else d.text
        if not body.strip():
            raise HTTPException(400, "Le message est vide.")

    @app.get("/api/campaigns/{campaign_id}/send-summary")
    def send_summary(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        s = settings()
        _, classes = analyze(campaign, campaign.draft.recipients_raw)
        count = len(classes.to_send)
        return {
            "count": count,
            "retry": len(classes.retry),
            "already_sent": len(classes.already_sent),
            "sender": s.email,
            "sender_name": s.display_name,
            "has_password": bool(password_store.get(s.email)),
            "label": campaign.draft.label.strip(),
            "subject": campaign.draft.subject,
            "mode": campaign.draft.mode,
            "attachments": attachments_info(campaign),
            "delay_seconds": s.delay_seconds,
            "estimate_seconds": estimate_seconds(count, s.delay_seconds),
            "over_limit": count > GMAIL_DAILY_LIMIT,
            "limit": GMAIL_DAILY_LIMIT,
        }

    @app.post("/api/campaigns/{campaign_id}/test-send")
    def test_send(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        check_draft(campaign)
        s, password = credentials()
        parsed = parse_recipients(campaign.draft.recipients_raw)
        preview = next((r for r in parsed.recipients if r.email == campaign.draft.preview_email), None)
        recipients = [preview] if preview else parsed.recipients[:1]
        try:
            send_test(build_config(campaign, password, s, recipients), smtp_factory=smtp_factory)
        except Exception as error:
            raise HTTPException(502, friendly_error(error))
        return {"ok": True, "message": f"Test envoyé à {s.email}."}

    @app.post("/api/campaigns/{campaign_id}/send", status_code=202)
    def start_send(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        if active_job():
            raise HTTPException(409, "Un envoi est déjà en cours.")
        check_draft(campaign)
        s, password = credentials()
        _, classes = analyze(campaign, campaign.draft.recipients_raw)
        if not classes.to_send:
            raise HTTPException(400, "Aucun destinataire à qui envoyer.")
        job = Job(config=build_config(campaign, password, s, classes.to_send),
                  smtp_factory=smtp_factory, imap_factory=imap_factory)
        jobs[job.id] = job
        job.start()
        return job.snapshot()

    @app.get("/api/jobs/current")
    def current_job():
        job = active_job() or (list(jobs.values())[-1] if jobs else None)
        return job.snapshot() if job else None

    def job_or_404(job_id: str) -> Job:
        if job_id not in jobs:
            raise HTTPException(404, "Envoi introuvable.")
        return jobs[job_id]

    @app.post("/api/jobs/{job_id}/{action}")
    def control_job(job_id: str, action: str):
        job = job_or_404(job_id)
        if action == "pause":
            job.pause()
        elif action == "resume":
            job.resume()
        elif action == "cancel":
            job.cancel()
        else:
            raise HTTPException(404, "Action inconnue.")
        return job.snapshot()

    @app.get("/api/jobs/{job_id}/log")
    def job_log(job_id: str):
        return job_or_404(job_id).events

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str, request: Request, after: int = 0):
        job = job_or_404(job_id)
        last = request.headers.get("last-event-id")
        seq = int(last) if last and last.isdigit() else after

        async def stream():
            nonlocal seq
            yield "retry: 2000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                events = await asyncio.to_thread(job.events_after, seq, 10.0)
                if not events:
                    if job.finished:
                        return
                    yield ": keep-alive\n\n"
                    continue
                for event in events:
                    seq = event["seq"]
                    yield f"id: {seq}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                if job.finished and seq >= len(job.events):
                    return

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------------- suivi
    @app.get("/api/campaigns/{campaign_id}/tracking")
    def get_tracking(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        t = tracking_mod.load(campaign.csv_path)
        return {
            "columns": t.columns,
            "rows": [{c: row.get(c) for c in t.columns} for row in t.rows.values()],
            "counts": t.counts(),
            "path": str(campaign.csv_path),
        }

    @app.patch("/api/campaigns/{campaign_id}/tracking")
    def edit_tracking(campaign_id: str, body: CellIn):
        campaign = campaign_or_404(campaign_id)
        ensure_not_sending(campaign_id)
        t = tracking_mod.load(campaign.csv_path)
        try:
            t.set_value(body.email, body.column, body.value)
        except KeyError:
            raise HTTPException(404, "Adresse absente du suivi.")
        except ValueError as error:
            raise HTTPException(400, str(error))
        tracking_mod.save(t, campaign.csv_path)
        return {"ok": True, "counts": t.counts()}

    @app.get("/api/campaigns/{campaign_id}/export")
    def export_tracking(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        data = tracking_mod.load(campaign.csv_path).to_csv_text().encode("utf-8-sig")
        filename = f"suivi-{campaign.id}.csv"
        return Response(data, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.post("/api/campaigns/{campaign_id}/check-replies")
    def check_replies(campaign_id: str):
        campaign = campaign_or_404(campaign_id)
        ensure_not_sending(campaign_id)
        label = campaign.draft.label.strip()
        if not label:
            raise HTTPException(400, "Cette campagne n'a pas de libellé Gmail : impossible de retrouver ses fils.")
        s, password = credentials()
        try:
            with ImapSession(s.email, password, factory=imap_factory) as imap:
                replies = imap.find_replies(label)
        except AuthError as error:
            raise HTTPException(502, str(error))
        except Exception as error:
            raise HTTPException(502, friendly_error(error))
        t = tracking_mod.load(campaign.csv_path)
        updated = []
        for email, when in replies.items():
            row = t.rows.get(email)
            if row and not row.values.get("reponse", "").strip():
                row.values["reponse"] = f"Répondu le {when:%Y-%m-%d}"
                updated.append(email)
        if updated:
            tracking_mod.save(t, campaign.csv_path)
        return {"found": len(replies), "updated": updated, "counts": t.counts()}

    # --------------------------------------------------------------------- front
    root = static_dir() if serve_static else None
    if root:
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(404)
            candidate = (root / full_path).resolve()
            if full_path and candidate.is_file() and root.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    app.state.jobs = jobs
    app.state.store = store
    return app
