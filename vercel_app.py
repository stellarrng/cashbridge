"""Vercel entry point: the FastAPI app as a Python serverless function.

Static pages (/, /app, /assets/*) are served by Vercel's CDN (see vercel.json); everything else,
including /api/*, reaches this function. Runtime files go to /tmp (config/runtime_mode.py).
"""

from api.main import app  # noqa: F401
