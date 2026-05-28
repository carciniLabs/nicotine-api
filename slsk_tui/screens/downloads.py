"""Downloads monitoring screen for Soulseek TUI."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Static
from textual.containers import Vertical

from slsk_tui.client import SlskClient, SlskApiError


def _human_size(size_bytes: int | float | None) -> str:
    """Convert bytes to a human-readable string."""
    if size_bytes is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _progress_pct(item: dict) -> str:
    """Compute progress percentage from size and progress (= current_byte_offset)."""
    total = item.get("size") or 0
    current = item.get("progress") or 0
    if not total:
        return "—" if not current else "0%"
    return f"{min(current / total * 100, 100):.0f}%"


class DownloadsScreen(Screen):
    """Screen showing current downloads with auto-refresh."""

    TITLE = "Downloads"

    BINDINGS = [
        Binding("c", "cancel_download", "Cancel", show=True),
        Binding("r", "rescan_shares", "Rescan", show=True),
        Binding("escape", "pop_screen", "Back", show=True),
    ]

    def __init__(self, client: SlskClient, **kwargs) -> None:
        super().__init__(**kwargs)
        self.client = client
        self._downloads_by_row: dict[str, dict] = {}  # row_key str -> download item

    def compose(self) -> ComposeResult:
        yield Vertical(
            DataTable(id="downloads-table"),
            Static("", id="downloads-status"),
        )

    def on_mount(self) -> None:
        """Set up the table and start auto-refresh."""
        table = self.query_one("#downloads-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Filename", "User", "Status", "Progress", "Speed", "Size")
        self._refresh_downloads()
        self.set_interval(5, self._refresh_downloads)

    # -- key pass-through for app bindings ----------------------------------

    def on_key(self, event) -> None:
        """Let app-level bindings (1, 2, q) work from this screen too."""
        key = event.key
        if key in ("1", "2", "q"):
            event.prevent_default()
            action_map = {"1": "show_search", "2": "show_downloads", "q": "quit"}
            action_name = action_map[key]
            self.app.run_action(action_name)

    # -- refresh logic ------------------------------------------------------

    def _refresh_downloads(self) -> None:
        """Fetch downloads from the API and update the table."""
        status_label = self.query_one("#downloads-status", Static)
        table = self.query_one("#downloads-table", DataTable)

        try:
            downloads = self.client.get_downloads()
        except (SlskApiError, Exception) as exc:
            status_label.update(f"[red]API error: {exc}[/red]")
            return

        if not downloads:
            table.clear()
            self._downloads_by_row.clear()
            status_label.update("[dim]No downloads[/dim]")
            return

        # Track which IDs are still present so we can remove stale rows
        current_ids: set[str] = set()

        for item in downloads:
            dl_id = str(item.get("id", id(item)))
            current_ids.add(dl_id)

            # Display just the filename basename for readability
            filename = item.get("filename", "—")
            display_name = os.path.basename(filename) if filename else "—"

            row_data = (
                display_name,
                item.get("user", "—"),
                item.get("status", "—"),
                _progress_pct(item),
                f"{item.get('speed_kbps', 0)} kbps",
                _human_size(item.get("size")),
            )

            if dl_id in self._downloads_by_row:
                # Update existing row
                table.update_row(dl_id, row_data)
            else:
                # Add new row, keyed by download id
                table.add_row(*row_data, key=dl_id)
                self._downloads_by_row[dl_id] = item

            # Keep item data fresh for cancel lookup
            self._downloads_by_row[dl_id] = item

        # Remove rows for downloads that no longer exist
        stale = set(self._downloads_by_row.keys()) - current_ids
        for old_id in stale:
            try:
                table.remove_row(old_id)
            except Exception:
                pass
            self._downloads_by_row.pop(old_id, None)

        status_label.update(f"[green]{len(downloads)} download(s)[/green]")

    def action_cancel_download(self) -> None:
        """Cancel the currently selected download after confirmation."""
        table = self.query_one("#downloads-table", DataTable)

        # Get the row key from the cursor row index
        cursor_row = table.cursor_row
        if cursor_row is None or cursor_row < 0:
            self.notify("No download selected", severity="warning")
            return

        try:
            row_key = table.get_row_at(cursor_row)
            # The row key IS the download id we set via key=dl_id in add_row
            dl_id = str(row_key) if not isinstance(row_key, str) else row_key
        except Exception:
            # Fallback: try getting the key from the ordered key list
            try:
                all_keys = list(table.rows.keys())
                dl_id = str(all_keys[cursor_row])
            except Exception:
                self.notify("Could not identify download", severity="warning")
                return

        # Get display info
        item = self._downloads_by_row.get(dl_id, {})
        display_name = os.path.basename(item.get("filename", dl_id))

        self.app.push_screen(
            ConfirmScreen(f"Cancel download: {display_name}?"),
            lambda confirmed, did=dl_id: self._do_cancel(did) if confirmed else None,
        )

    def _do_cancel(self, dl_id: str) -> None:
        """Actually cancel the download."""
        try:
            self.client.cancel_download(dl_id)
            self.notify("Download cancelled", severity="information")
            self._refresh_downloads()
        except SlskApiError as exc:
            self.notify(f"Cancel failed: {exc}", severity="error")

    def action_rescan_shares(self) -> None:
        """Trigger a share rescan."""
        try:
            result = self.client.rescan_shares()
            if result.get("success") or result.get("status") == "rescan_started":
                self.notify("Rescan triggered", severity="information")
            else:
                self.notify(f"Rescan issue: {result}", severity="warning")
        except SlskApiError as exc:
            self.notify(f"Rescan failed: {exc}", severity="error")
        except Exception as exc:
            self.notify(f"Rescan failed: {exc}", severity="error")


class ConfirmScreen(Screen):
    """Simple yes/no confirmation modal."""

    BINDINGS = [
        Binding("y", "confirm", "Yes", show=False),
        Binding("n", "deny", "No", show=False),
        Binding("escape", "deny", "No", show=False),
    ]

    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = message

    def compose(self) -> ComposeResult:
        yield Static(f"\n  {self.message}  [Y/n]  \n")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)