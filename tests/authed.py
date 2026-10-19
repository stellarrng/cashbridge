"""Test helper: a TestClient signed in as the SYNTHETIC demo personas.

Routes are mapped to the persona that is allowed to call them, the way the web UI does it:
the Director approves, the bank reviewer uses /api/bank/*, the Chief accountant does everything
else. Pass an explicit ``Authorization`` header (or ``as_user=``) to test refusals.
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse

from fastapi.testclient import TestClient

DIRECTOR_PATHS = {"/api/approve", "/api/reject_pack"}
PERSONAS = ("sme.lan", "sme.minh", "bank.lihua")


class RoleClient(TestClient):
    def __init__(self, app: Any, **kwargs: Any) -> None:
        super().__init__(app, **kwargs)
        self.tokens = {}
        for user in PERSONAS:
            response = super().request("POST", "/api/auth/demo-login", json={"user_id": user})
            assert response.status_code == 200, response.text
            self.tokens[user] = response.json()["token"]
        self.as_user: Optional[str] = None

    @staticmethod
    def persona_for(path: str) -> Optional[str]:
        if path.startswith("/api/auth/") or path.startswith("/api/automation/") or path in ("/api/health", "/api/public/overview"):
            return None
        if path in DIRECTOR_PATHS or (path.startswith("/packs/") and path.endswith("/approve")):
            return "sme.minh"
        if path.startswith("/api/bank/") and path != "/api/bank/review":
            return "bank.lihua"
        return "sme.lan"

    def header(self, user: str) -> dict:
        return {"Authorization": "Bearer " + self.tokens[user]}

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any):  # type: ignore[override]
        headers = dict(kwargs.pop("headers", None) or {})
        if not any(k.lower() == "authorization" for k in headers):
            user = self.as_user or self.persona_for(urlparse(str(url)).path)
            if user:
                headers.update(self.header(user))
        return super().request(method, url, *args, headers=headers, **kwargs)
