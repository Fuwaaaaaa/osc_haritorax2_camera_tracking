"""Unified entry point for PyInstaller — launches any osc_tracking tool.

Usage:
    osc_tools.exe setup_wizard
    osc_tools.exe benchmark --cam1 0 --cam2 1
    osc_tools.exe preview --cam1 0 --cam2 1
    osc_tools.exe calibrate
    osc_tools.exe connection_check
    osc_tools.exe osc_monitor
    osc_tools.exe download_model
    osc_tools.exe simulate
    osc_tools.exe checkerboard
"""
import sys
import os

if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
else:
    base = os.path.dirname(os.path.abspath(__file__))

src_path = os.path.join(base, "src")
if os.path.isdir(src_path):
    sys.path.insert(0, src_path)

TOOLS = {
    "setup_wizard": "osc_tracking.tools.setup_wizard",
    "benchmark": "osc_tracking.tools.benchmark",
    "preview": "osc_tracking.tools.preview",
    "calibrate": "osc_tracking.tools.calibrate",
    "connection_check": "osc_tracking.tools.connection_check",
    "osc_monitor": "osc_tracking.tools.osc_monitor",
    "download_model": "osc_tracking.tools.download_model",
    "simulate": "osc_tracking.tools.simulate",
    "checkerboard": "osc_tracking.tools.generate_checkerboard",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("OSC Tracking Tools")
        print()
        print("使い方: osc_tools.exe <ツール名> [オプション]")
        print()
        print("利用可能なツール:")
        for name in TOOLS:
            print(f"  {name}")
        print()
        print("例:")
        print("  osc_tools.exe setup_wizard")
        print("  osc_tools.exe benchmark --cam1 0 --cam2 1 --duration 60")
        print("  osc_tools.exe preview --cam1 0 --cam2 1")
        print("  osc_tools.exe connection_check --port 6969")
        return

    tool_name = sys.argv[1]
    if tool_name not in TOOLS:
        print(f"エラー: 不明なツール '{tool_name}'")
        print(f"利用可能: {', '.join(TOOLS.keys())}")
        sys.exit(1)

    # Remove tool name from argv so the tool's argparse works correctly
    sys.argv = [sys.argv[0]] + sys.argv[2:]

    module = __import__(TOOLS[tool_name], fromlist=["main"])
    module.main()


if __name__ == "__main__":
    main()
