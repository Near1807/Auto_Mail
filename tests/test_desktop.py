import sys

import pytest

from desktop.instance import InstanceLock
from desktop.main import Backend, free_port


@pytest.mark.skipif(sys.platform == "win32", reason="le mutex Windows est testé par l'exe en CI")
def test_second_instance_is_refused(tmp_path):
    first, second = InstanceLock(tmp_path), InstanceLock(tmp_path)
    assert first.acquire()
    first.publish(1234)
    assert not second.acquire()
    first.release()
    assert not (tmp_path / "instance.json").exists()
    assert second.acquire()
    second.release()


def test_focus_existing_without_instance(tmp_path):
    assert InstanceLock(tmp_path).focus_existing() is False


def test_backend_serves_health_on_free_port(monkeypatch):
    import urllib.request

    from fastapi import FastAPI

    # Le garde réseau des tests bloque create_connection : on le lève pour parler à 127.0.0.1.
    monkeypatch.undo()
    app = FastAPI()
    app.get("/api/health")(lambda: {"ok": True})
    backend = Backend(app)
    backend.start()
    try:
        assert backend.url.startswith("http://127.0.0.1:")
        with urllib.request.urlopen(backend.url + "/api/health", timeout=5) as r:
            assert r.status == 200
    finally:
        backend.stop()
    assert isinstance(free_port(), int)
