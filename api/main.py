"""Point d'entrée ``uvicorn api.main:app`` (développement).

``AUTOMAIL_DEMO=1`` branche un faux Gmail : rien ne part, pratique pour essayer l'interface.
"""

import os

from .app import create_app


def build():
    if os.environ.get("AUTOMAIL_DEMO") == "1":
        from core.settings import PasswordStore

        from . import demo

        return create_app(smtp_factory=demo.DemoSmtp, imap_factory=demo.DemoImap,
                          passwords=PasswordStore(demo.memory_keyring))
    return create_app()


app = build()
