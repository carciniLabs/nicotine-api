"""Soulseek TUI — Textual app with screen navigation."""

from __future__ import annotations

import os

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static

from slsk_tui.client import SlskClient
from slsk_tui.widgets.status_bar import StatusBar
from slsk_tui.screens.search import SearchScreen
from slsk_tui.screens.downloads import DownloadsScreen
from slsk_tui.screens.splash import SplashScreen


class SlskTUI(App):
    """Soulseek TUI client"""

    TITLE = "Soulseek TUI"
    SUB_TITLE = "slsk-api frontend"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        ("1", "show_search", "Search"),
        ("2", "show_downloads", "Downloads"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, client: SlskClient | None = None, base_url: str | None = None) -> None:
        super().__init__()
        resolved_url = base_url or os.environ.get("SLSK_API_URL", "http://localhost:3090")
        self.client = client or SlskClient(base_url=resolved_url)
        self._downloads_installed = False
        self._splash_shown = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusBar()
        # Search is the default screen (mounted as the base content)
        yield SearchScreen()
        yield Footer()

    def on_mount(self) -> None:
        """Show splash screen on first launch, then transition to the main app."""
        if not self._splash_shown:
            self._splash_shown = True
            # Hide header/status/footer during splash for a clean overlay
            try:
                self.query_one(Header).display = False
                self.query_one(StatusBar).display = False
                self.query_one(Footer).display = False
            except Exception:
                pass
            self.push_screen(SplashScreen(), callback=self._on_splash_dismiss)

    def _on_splash_dismiss(self, result) -> None:
        """Called when SplashScreen dismisses — restore header/status/footer."""
        try:
            self.query_one(Header).display = True
            self.query_one(StatusBar).display = True
            self.query_one(Footer).display = True
        except Exception:
            pass

    def on_unmount(self) -> None:
        self.client.close()

    # -- screen navigation ---------------------------------------------------

    def action_show_search(self) -> None:
        """Pop back to the base (Search) screen."""
        while len(self.screen_stack) > 1:
            self.pop_screen()

    def action_show_downloads(self) -> None:
        """Push or switch to the Downloads screen."""
        # If already on downloads, do nothing
        if len(self.screen_stack) > 1 and isinstance(self.screen_stack[-1], DownloadsScreen):
            return

        if not self._downloads_installed:
            self.install_screen(DownloadsScreen(self.client), name="downloads")
            self._downloads_installed = True

        # Pop any non-base screen first (e.g. another Downloads instance shouldn't stack)
        while len(self.screen_stack) > 1:
            self.pop_screen()

        self.push_screen("downloads")