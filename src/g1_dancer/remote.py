from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RemoteError(RuntimeError):
    pass


class RemoteClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self, method: str, path: str, data: bytes | None = None, *, safety_confirmed: bool = False
    ) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if safety_confirmed:
            headers["X-G1-Safety-Confirmed"] = "YES"
        request = Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urlopen(request, timeout=120) as response:
                return json.loads(response.read())
        except HTTPError as exc:
            try:
                detail = json.loads(exc.read()).get("error", exc.reason)
            except Exception:
                detail = exc.reason
            raise RemoteError(f"Server returned {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RemoteError(f"Cannot reach {self.base_url}: {exc.reason}") from exc

    def upload(self, routine_id: str, path: Path) -> Dict[str, Any]:
        if path.suffix.lower() != ".mp3" or not path.is_file():
            raise RemoteError("Upload must be an existing .mp3 file")
        data = path.read_bytes()
        return self.request("PUT", f"/api/routines/{routine_id}/audio", data)
