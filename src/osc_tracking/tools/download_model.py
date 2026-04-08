"""Download MediaPipe Pose Landmarker model.

Usage:
    python -m osc_tracking.tools.download_model [--lite]
"""

import argparse
import sys
import urllib.request
from pathlib import Path

MODELS = {
    "heavy": {
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_heavy/float16/latest/pose_landmarker_heavy.task",
        "path": "models/pose_landmarker_heavy.task",
        "desc": "High accuracy (best for seated/lying positions)",
    },
    "full": {
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task",
        "path": "models/pose_landmarker_full.task",
        "desc": "Balanced accuracy and speed",
    },
    "lite": {
        "url": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
        "path": "models/pose_landmarker_lite.task",
        "desc": "Fastest, lower accuracy (fallback)",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Download MediaPipe model")
    parser.add_argument(
        "--variant", choices=["heavy", "full", "lite", "all"], default="heavy",
        help="Model variant to download (default: heavy)",
    )
    args = parser.parse_args()

    Path("models").mkdir(exist_ok=True)

    variants = list(MODELS.keys()) if args.variant == "all" else [args.variant]

    for variant in variants:
        info = MODELS[variant]
        path = Path(info["path"])

        if path.exists():
            print(f"  {variant}: already exists at {path}")
            continue

        print(f"  Downloading {variant} ({info['desc']})...")
        try:
            urllib.request.urlretrieve(info["url"], path, _progress)
            print(f"\n  Saved to {path}")
        except Exception as e:
            print(f"\n  Failed: {e}")
            sys.exit(1)

    print("\nDone! Models ready.")


def _progress(block, block_size, total):
    downloaded = block * block_size
    if total > 0:
        pct = min(downloaded * 100 / total, 100)
        mb = downloaded / 1024 / 1024
        total_mb = total / 1024 / 1024
        print(f"\r  {mb:.1f}/{total_mb:.1f} MB ({pct:.0f}%)", end="", flush=True)


if __name__ == "__main__":
    main()
