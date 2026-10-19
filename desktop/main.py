"""Lancement de l'application de bureau.

    AutoMail.exe               ouvre la fenêtre
    AutoMail.exe --self-test   démarre le back, vérifie /api/health, le front et keyring,
                               puis quitte avec le code 0 (tout va bien) ou 1
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core import paths
from core.version import __version__

from .instance import WINDOW_TITLE, InstanceLock

log = logging.getLogger("automail")


def logs_dir() -> Path:
    path = paths.data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging() -> Path:
    log_file = logs_dir() / "automail.log"
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:  # l'exe sans console n'a pas de stderr
        root.addHandler(logging.StreamHandler())
    return log_file


def show_error(title: str, message: str) -> None:
    """Boîte de dialogue lisible, même si la fenêtre principale n'a jamais pu s'ouvrir."""
    log.error("%s: %s", title, message)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)  # MB_ICONERROR
    elif sys.stderr is not None:
        print(f"{title}\n{message}", file=sys.stderr)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Backend:
    """Serveur uvicorn dans un thread, sur 127.0.0.1 et un port libre."""

    def __init__(self, app):
        import uvicorn

        self.app = app
        self.port = free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_config=None,
                                access_log=False, lifespan="off")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, name="uvicorn", daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 20.0) -> None:
        self.thread.start()
        deadline = time.monotonic() + timeout
        while not self.server.started:
            if not self.thread.is_alive():
                raise RuntimeError("Le serveur interne s'est arrêté au démarrage (voir le journal).")
            if time.monotonic() > deadline:
                raise RuntimeError(f"Le serveur interne n'a pas démarré en {timeout:.0f} s.")
            time.sleep(0.05)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(5)


class Bridge:
    """Fonctions appelables depuis le front via ``window.pywebview.api``."""

    def __init__(self, app):
        self._app = app
        self._window = None

    def save_export(self, campaign_id: str) -> dict:
        """Boîte « Enregistrer sous » Windows, puis écrit le CSV de suivi."""
        import webview

        from core import tracking

        campaign = self._app.state.store.get(campaign_id)
        dialog = getattr(getattr(webview, "FileDialog", None), "SAVE", None) or webview.SAVE_DIALOG
        result = self._window.create_file_dialog(
            dialog, save_filename=f"suivi-{campaign.id}.csv", file_types=("Fichier CSV (*.csv)", "Tous les fichiers (*.*)"))
        if not result:
            return {"ok": False, "cancelled": True}
        target = Path(result if isinstance(result, str) else result[0])
        if target.suffix.lower() != ".csv":
            target = target.with_suffix(".csv")
        try:
            target.write_bytes(tracking.load(campaign.csv_path).to_csv_text().encode("utf-8-sig"))
        except PermissionError:
            return {"ok": False, "message": f"Impossible d'écrire « {target.name} » : le fichier est peut-être ouvert dans Excel."}
        log.info("Suivi exporté vers %s", target)
        return {"ok": True, "path": str(target)}


def build_app():
    from api.app import create_app_from_env

    return create_app_from_env()


def self_test() -> int:
    """Vérifie que l'exe contient tout ce qu'il faut. Code de sortie 0 ou 1."""
    checks: list[tuple[str, bool, str]] = []
    backend = None
    try:
        backend = Backend(build_app())
        backend.start()
        with urllib.request.urlopen(backend.url + "/api/health", timeout=5) as r:
            body = r.read().decode()
            checks.append(("api /health", r.status == 200 and '"ok":true' in body.replace(" ", ""), body))
        with urllib.request.urlopen(backend.url + "/", timeout=5) as r:
            page = r.read().decode()
            ok = r.status == 200 and '<div id="root">' in page
            checks.append(("front index.html", ok, f"{len(page)} octets"))
        import re

        asset = re.search(r'src="(/assets/[^"]+\.js)"', page)
        if asset:
            with urllib.request.urlopen(backend.url + asset.group(1), timeout=5) as r:
                checks.append(("front assets", r.status == 200 and len(r.read()) > 1000, asset.group(1)))
        else:
            checks.append(("front assets", False, "aucun script dans index.html"))
    except Exception as error:
        checks.append(("serveur", False, f"{error.__class__.__name__}: {error}"))
    finally:
        if backend:
            backend.stop()

    try:
        import keyring

        service, user, secret = "AutoMail-self-test", "self-test", f"ok-{time.time():.0f}"
        keyring.set_password(service, user, secret)
        read_back = keyring.get_password(service, user)
        keyring.delete_password(service, user)
        backend_name = type(keyring.get_keyring()).__module__ + "." + type(keyring.get_keyring()).__name__
        checks.append(("keyring", read_back == secret, backend_name))
    except Exception as error:
        checks.append(("keyring", False, f"{error.__class__.__name__}: {error}"))

    try:
        import webview  # noqa: F401

        if sys.platform == "win32":
            import webview.platforms.edgechromium  # noqa: F401
        checks.append(("pywebview", True, ""))
    except Exception as error:
        checks.append(("pywebview", False, f"{error.__class__.__name__}: {error}"))

    for name, ok, detail in checks:
        log.info("self-test %-16s %s %s", name, "OK " if ok else "ÉCHEC", detail)
    success = all(ok for _, ok, _ in checks)
    log.info("self-test : %s (Auto Mail %s)", "réussi" if success else "échoué", __version__)
    return 0 if success else 1


def run_window() -> int:
    import webview

    lock = InstanceLock(paths.data_dir())
    if not lock.acquire():
        log.info("Auto Mail est déjà ouvert : on remet sa fenêtre au premier plan.")
        lock.focus_existing()
        return 0

    try:
        app = build_app()
        backend = Backend(app)
        backend.start()
        lock.publish(backend.port)
        log.info("Auto Mail %s : serveur sur %s", __version__, backend.url)

        bridge = Bridge(app)
        window = webview.create_window(WINDOW_TITLE, backend.url, js_api=bridge, width=1280, height=820,
                                       resizable=True, min_size=(960, 640), background_color="#F6F2EC",
                                       text_select=True)
        bridge._window = window

        def bring_to_front():
            try:
                window.restore()
                window.show()
                window.on_top = True
                window.on_top = False
            except Exception as error:
                log.warning("Premier plan impossible : %s", error)

        app.state.on_focus = bring_to_front
        debug_port = os.environ.get("AUTOMAIL_REMOTE_DEBUGGING_PORT")
        if debug_port:  # tests de bout en bout uniquement (Playwright s'attache à WebView2)
            webview.settings["REMOTE_DEBUGGING_PORT"] = int(debug_port)
        storage = paths.data_dir() / "webview"
        storage.mkdir(exist_ok=True)
        # private_mode=False : le thème, la campagne ouverte… survivent d'un lancement à l'autre.
        webview.start(private_mode=False, storage_path=str(storage))
        backend.stop()
        return 0
    finally:
        lock.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="AutoMail")
    parser.add_argument("--self-test", action="store_true", help="vérifie l'installation puis quitte (0 = OK)")
    args = parser.parse_args(argv)
    log_file = None
    try:
        log_file = setup_logging()
        if args.self_test:
            return self_test()
        return run_window()
    except Exception:
        details = traceback.format_exc()
        log.error("Erreur au démarrage :\n%s", details)
        where = f"\n\nLe détail est dans :\n{log_file}" if log_file else ""
        last_line = details.strip().splitlines()[-1]
        if not args.self_test:
            show_error("Auto Mail n'a pas pu démarrer", f"{last_line}{where}")
        return 1
