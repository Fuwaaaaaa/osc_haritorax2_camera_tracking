"""Entry point for PyInstaller — launches osc_tracking.main."""
import os
import sys

# Add src to path so osc_tracking package is importable
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
else:
    base = os.path.dirname(os.path.abspath(__file__))

src_path = os.path.join(base, "src")
if os.path.isdir(src_path):
    sys.path.insert(0, src_path)

from osc_tracking.main import main  # noqa: E402

main()
