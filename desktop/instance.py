"""Une seule instance d'Auto Mail à la fois.

La première instance prend un verrou (mutex nommé sous Windows, ``flock`` ailleurs) et
note son port dans ``instance.json``. Une deuxième instance demande à la première de
remettre sa fenêtre au premier plan, puis quitte.
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)
WINDOW_TITLE = "Auto Mail"
_MUTEX_NAME = "Local\\AutoMail-single-instance"


class InstanceLock:
    def __init__(self, data_dir: Path):
        self.info_file = data_dir / "instance.json"
        self.lock_file = data_dir / "instance.lock"
        self._handle = None

    def acquire(self) -> bool:
        """True si aucune autre instance ne tourne (le verrou est alors gardé jusqu'à la fin)."""
        if sys.platform == "win32":
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            already = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
            if already:
                kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        import fcntl

        handle = open(self.lock_file, "w")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def publish(self, port: int) -> None:
        self.info_file.write_text(json.dumps({"port": port}), encoding="utf-8")

    def release(self) -> None:
        try:
            self.info_file.unlink(missing_ok=True)
        except OSError:
            pass
        if self._handle is None:
            return
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.CloseHandle(self._handle)
        else:
            self._handle.close()
        self._handle = None

    def focus_existing(self) -> bool:
        """Demande à l'instance déjà ouverte de se montrer. True si elle a répondu."""
        try:
            port = json.loads(self.info_file.read_text(encoding="utf-8"))["port"]
            request = urllib.request.Request(f"http://127.0.0.1:{port}/api/app/focus", method="POST", data=b"")
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception as error:  # fichier absent, instance en cours de démarrage…
            log.info("Instance existante injoignable par HTTP : %s", error)
        return _focus_window_by_title()


def _focus_window_by_title() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True
