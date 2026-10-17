"""Point d'entrée ``uvicorn api.main:app`` (développement)."""

from .app import create_app

app = create_app()
