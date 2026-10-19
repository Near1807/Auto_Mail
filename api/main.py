"""Point d'entrée ``uvicorn api.main:app`` (développement).

``AUTOMAIL_DEMO=1`` branche un faux Gmail : rien ne part, pratique pour essayer l'interface.
"""

from .app import create_app_from_env

app = create_app_from_env()
