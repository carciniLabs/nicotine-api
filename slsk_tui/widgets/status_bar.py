"""Status bar widget — shows connection state, username, shares count."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widgets import Static


class _StatusSegment(Static):
    """A single segment in the status bar."""
    pass


class StatusBar(Horizontal):
    """Bar showing connection status, username, and shares count.

    Auto-refreshes every 10 seconds via ``set_interval``.
    """

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $panel;
        color: $text;
        padding: 0 1;

        _StatusSegment {
            padding: 0 1;
            height: 1;
        }
    }
    """

    connected: reactive[bool] = reactive(False)
    username: reactive[str] = reactive("")
    shares_count: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        self._conn_seg = _StatusSegment(id="conn-status")
        self._user_seg = _StatusSegment(id="user-status")
        self._shares_seg = _StatusSegment(id="shares-status")
        yield self._conn_seg
        yield self._user_seg
        yield self._shares_seg

    def on_mount(self) -> None:
        self._refresh_status()
        self.set_interval(10, self._refresh_status)

    def _refresh_status(self) -> None:
        """Poll the API client for current status."""
        try:
            status = self.app.client.get_status()  # type: ignore[attr-defined]
            self.connected = status.get("connected", False)
            self.username = status.get("username", "")
            self.shares_count = status.get("shares_count", 0)
        except Exception:
            self.connected = False
            self.username = ""
            self.shares_count = 0

    def watch_connected(self, connected: bool) -> None:
        if connected:
            self._conn_seg.update("[green]\u25cf Connected[/green]")
        else:
            self._conn_seg.update("[red]\u25cf Disconnected[/red]")

    def watch_username(self, username: str) -> None:
        if username:
            self._user_seg.update(f"User: {username}")
        else:
            self._user_seg.update("")

    def watch_shares_count(self, count: int) -> None:
        self._shares_seg.update(f"Shares: {count}")