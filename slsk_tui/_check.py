#!/usr/bin/env python3
"""Quick smoke test — verify all slsk_tui imports work."""
import sys
sys.path.insert(0, "/home/crab/dev/nicotine-api")

try:
    from slsk_tui.app import SlskTUI
    print("OK: app.SlskTUI")
except Exception as e:
    print(f"FAIL: app.SlskTUI: {e}")

try:
    from slsk_tui.client import SlskClient, SlskApiError
    print("OK: client.SlskClient, SlskApiError")
except Exception as e:
    print(f"FAIL: client: {e}")

try:
    from slsk_tui.screens.search import SearchScreen, _format_bitrate, _human_size
    print("OK: screens.search.SearchScreen")
except Exception as e:
    print(f"FAIL: screens.search: {e}")

try:
    from slsk_tui.screens.downloads import DownloadsScreen, ConfirmScreen
    print("OK: screens.downloads.DownloadsScreen, ConfirmScreen")
except Exception as e:
    print(f"FAIL: screens.downloads: {e}")

try:
    from slsk_tui.widgets.status_bar import StatusBar
    print("OK: widgets.status_bar.StatusBar")
except Exception as e:
    print(f"FAIL: widgets.status_bar: {e}")

# Verify _format_bitrate
print("\n_format_bitrate tests:")
for val, expected in [("FLAC", "FLAC"), (320, "320"), (1411, "1"), (0, "0"), ("", ""), (None, "")]:
    result = _format_bitrate(val)
    status = "PASS" if result == expected else f"FAIL (got {result!r})"
    print(f"  {val!r} -> {expected!r}: {status}")

# Verify _human_size
print("\n_human_size tests:")
for val, expected in [(0, "0 Bytes"), (1024, "1.0 KiB"), (1048576, "1.0 MiB")]:
    result = _human_size(val)
    status = "PASS" if result == expected else f"FAIL (got {result!r})"
    print(f"  {val} -> {expected!r}: {status}")

# Check styles.tcss exists
import os
tcss = "/home/crab/dev/nicotine-api/slsk_tui/styles.tcss"
if os.path.exists(tcss):
    print(f"\nOK: styles.tcss exists ({os.path.getsize(tcss)} bytes)")
else:
    print(f"\nFAIL: styles.tcss not found")

# Check README exists
readme = "/home/crab/dev/nicotine-api/slsk_tui/README.md"
if os.path.exists(readme):
    print(f"OK: README.md exists ({os.path.getsize(readme)} bytes)")
else:
    print("FAIL: README.md not found")

# Check SLSK_API_URL is respected
os.environ["SLSK_API_URL"] = "http://test:1234"
app = SlskTUI()
assert app.client.base_url == "http://test:1234", f"Expected http://test:1234, got {app.client.base_url}"
print("OK: SLSK_API_URL env var works")
del os.environ["SLSK_API_URL"]
app2 = SlskTUI()
assert app2.client.base_url == "http://archbox:3090", f"Expected http://archbox:3090, got {app2.client.base_url}"
print("OK: default base_url is http://archbox:3090")

print("\nAll smoke tests complete.")