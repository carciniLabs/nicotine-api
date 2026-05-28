"""Entry point for python -m slsk_tui."""
import sys
import os

# Ensure the parent directory is on the path so `slsk_tui` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slsk_tui.app import SlskTUI

app = SlskTUI()
app.run()