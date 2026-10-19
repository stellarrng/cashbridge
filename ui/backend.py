"""Entry point the web layer imports: ``from ui.backend import get_backend``."""

from ui.backend_real import RealBackend, get_backend

__all__ = ["RealBackend", "get_backend"]
