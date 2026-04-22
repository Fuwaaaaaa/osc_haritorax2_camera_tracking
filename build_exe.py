"""Build executable files using PyInstaller.

Usage:
    python build_exe.py          # Build all executables
    python build_exe.py --main   # Build main app only
    python build_exe.py --tools  # Build tools only

Output: dist/ directory with all .exe files
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Executables to build: (output_name, entry_script, description)
MAIN_TARGETS = [
    ("osc_tracking", "entry_main.py", "Main tracking application"),
]

TOOL_TARGETS = [
    ("osc_tools", "entry_tools.py", "All tools (setup_wizard, benchmark, preview, etc.)"),
]

# Data files to bundle alongside the exe
DATA_FILES = [
    ("config/default.json", "config"),
    ("docs/haritora-setup-guide.md", "docs"),
]

# Hidden imports that PyInstaller misses
HIDDEN_IMPORTS = [
    "scipy.spatial.transform",
    "scipy.spatial.transform._rotation",
    "mediapipe",
    "cv2",
    "pythonosc",
    "pythonosc.dispatcher",
    "pythonosc.osc_server",
    "pythonosc.osc_message_builder",
    "osc_tracking",
    "osc_tracking.complementary_filter",
    "osc_tracking.config",
    "osc_tracking.camera_tracker",
    "osc_tracking.fusion_engine",
    "osc_tracking.osc_receiver",
    "osc_tracking.osc_sender",
    "osc_tracking.state_machine",
    "osc_tracking.visual_compass",
    "osc_tracking.quality_meter",
    "osc_tracking.web_dashboard",
    "osc_tracking.notifications",
    "osc_tracking.gesture_detector",
    "osc_tracking.motion_smoothing",
    "osc_tracking.profiler",
    "osc_tracking.stereo_calibration",
    # BLE direct receiver (experimental) — bleak imports Windows Runtime
    # bindings lazily, so PyInstaller needs explicit hints to bundle them.
    "osc_tracking.ble_receiver",
    "osc_tracking.receiver_protocol",
    "osc_tracking.tracker_mapping",
    "bleak",
    "bleak.backends.winrt",
    "bleak.backends.winrt.client",
    "bleak.backends.winrt.scanner",
    "bleak.backends.winrt.util",
]


def build_one(name: str, script: str, is_console: bool = True) -> bool:
    """Build a single executable."""
    print(f"\n{'=' * 50}")
    print(f"  Building: {name}.exe")
    print(f"  Source:   {script}")
    print(f"{'=' * 50}\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--name", name,
        "--onedir",
        "--console" if is_console else "--windowed",
        # Add src to Python path
        "--paths", "src",
    ]

    # Add hidden imports
    for imp in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", imp])

    # Add data files
    for src_path, dest_dir in DATA_FILES:
        if Path(src_path).exists():
            cmd.extend(["--add-data", f"{src_path};{dest_dir}"])

    # Add models directory if it exists
    if Path("models").exists():
        cmd.extend(["--add-data", "models;models"])

    # Add src package so imports work
    cmd.extend(["--add-data", "src/osc_tracking;osc_tracking"])

    cmd.append(script)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  FAILED: {name}")
        return False

    print(f"  SUCCESS: dist/{name}/{name}.exe")
    return True


def copy_config_to_dist(name: str) -> None:
    """Copy config files next to the exe for easy editing."""
    dist_dir = Path("dist") / name
    if not dist_dir.exists():
        return

    # Config
    config_dir = dist_dir / "config"
    config_dir.mkdir(exist_ok=True)
    src_config = Path("config/default.json")
    if src_config.exists():
        shutil.copy2(src_config, config_dir / "default.json")

    # Create empty user config placeholder
    user_config = config_dir / "user.json"
    if not user_config.exists():
        user_config.write_text("{}\n")


def main():
    parser = argparse.ArgumentParser(description="Build OSC Tracking executables")
    parser.add_argument("--main", action="store_true", help="Build main app only")
    parser.add_argument("--tools", action="store_true", help="Build tools only")
    args = parser.parse_args()

    if not args.main and not args.tools:
        # Build everything
        targets = MAIN_TARGETS + TOOL_TARGETS
    elif args.main:
        targets = MAIN_TARGETS
    else:
        targets = TOOL_TARGETS

    print(f"Building {len(targets)} executable(s)...\n")

    results = {}
    for name, script, desc in targets:
        ok = build_one(name, script)
        results[name] = ok
        if ok:
            copy_config_to_dist(name)

    # Summary
    print(f"\n{'=' * 50}")
    print("  Build Summary")
    print(f"{'=' * 50}")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"  [{status}] {name}.exe")
    print(f"\n  {passed}/{total} succeeded")
    print("  Output: dist/")
    print()

    if passed == total:
        print("  使い方:")
        print("  1. dist/osc_tracking/ フォルダを任意の場所にコピー")
        print("  2. models/ フォルダにMediaPipeモデルを配置")
        print("     (osc_tools.exe download_model でダウンロード可能)")
        print("  3. osc_tracking.exe を実行（メインアプリ）")
        print("  4. osc_tools.exe <ツール名> でツールを実行")
        print("     例: osc_tools.exe setup_wizard")
        print()

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
