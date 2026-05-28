"""HTTP client for the slsk-api REST API."""

from __future__ import annotations

import httpx


class SlskApiError(Exception):
    """Raised when the slsk-api returns a non-2xx response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"slsk-api error {status_code}: {message}")


class SlskClient:
    """Sync HTTP client wrapping all slsk-api endpoints."""

    def __init__(self, base_url: str = "http://localhost:3090") -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(base_url=self.base_url, timeout=10.0)

    # -- internal helpers ---------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = self._client.request(method, path, **kwargs)
        if resp.status_code >= 300:
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                detail = resp.text
            raise SlskApiError(resp.status_code, detail)
        return resp

    # -- public API ---------------------------------------------------------

    def health_check(self) -> bool:
        """Return True if the API is reachable, False otherwise (no raise)."""
        try:
            self.get_status()
            return True
        except Exception:
            return False

    def get_status(self) -> dict:
        """GET /status — connection status and stats."""
        return self._request("GET", "/status").json()

    def search(self, query: str, max_results: int = 20) -> dict:
        """POST /search — search Soulseek for a query. Returns full response dict."""
        return self._request(
            "POST", "/search", json={"query": query, "max_results": max_results},
            timeout=30.0,
        ).json()

    def download(self, user: str, file: str, filename: str) -> dict:
        """POST /download — queue a file for download."""
        return self._request(
            "POST", "/download", json={"user": user, "file": file, "filename": filename}
        ).json()

    def get_downloads(self) -> list[dict]:
        """GET /downloads — list active downloads. Returns the `downloads` list."""
        return self._request("GET", "/downloads").json().get("downloads", [])

    def cancel_download(self, transfer_id: str) -> bool:
        """DELETE /download/{id} — cancel a download. Returns True on success."""
        self._request("DELETE", f"/download/{transfer_id}")
        return True

    def rescan_shares(self) -> dict:
        """POST /rescan-shares — trigger a share rescan."""
        return self._request("POST", "/rescan-shares").json()

    def get_shares(self) -> list:
        """GET /shares — list configured shared folders."""
        return self._request("GET", "/shares").json()

    # -- cleanup ------------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SlskClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()