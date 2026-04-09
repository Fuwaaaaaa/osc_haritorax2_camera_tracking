"""Setup wizard — guided first-time setup for new users.

Walks through 7 steps: SlimeTora install, SlimeVR Server, camera
placement, stereo calibration, MediaPipe model, OSC connection check,
and first launch.

Usage:
    python -m osc_tracking.tools.setup_wizard
"""

import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

STEPS = [
    {
        "title": "SlimeToraのインストール",
        "description": (
            "HaritoraX2をPCに接続するためのブリッジソフトウェアです。\n"
            "https://github.com/OCSYT/SlimeTora からダウンロードしてください。\n"
            "既にインストール済みの場合はスキップできます。"
        ),
        "check": None,  # Manual check
    },
    {
        "title": "SlimeVR Serverのインストール",
        "description": (
            "SlimeToraからのデータをOSCプロトコルで出力するサーバーです。\n"
            "https://github.com/SlimeVR/SlimeVR-Server からダウンロード。\n"
            "OSC出力をポート6969に設定してください。"
        ),
        "check": None,
    },
    {
        "title": "カメラ配置",
        "description": (
            "Webカメラを2台設置します。\n"
            "推奨: 0.5-1m間隔で並べるか、90度の角度で配置。\n"
            "両方のカメラから全身が見えることを確認してください。"
        ),
        "check": "check_cameras",
    },
    {
        "title": "MediaPipeモデルのダウンロード",
        "description": (
            "ポーズ推定に必要なMediaPipeモデルをダウンロードします。\n"
            "自動的にダウンロードされます。"
        ),
        "check": "check_model",
    },
    {
        "title": "ステレオキャリブレーション",
        "description": (
            "2台のカメラの位置関係を計算します。\n"
            "チェッカーボード（同梱）を印刷し、両カメラの視野内で\n"
            "複数角度から撮影してください。"
        ),
        "check": "check_calibration",
    },
    {
        "title": "OSC接続確認",
        "description": (
            "SlimeVR ServerからのOSCデータを受信できるか確認します。\n"
            "SlimeTora + SlimeVR Serverを起動してから実行してください。"
        ),
        "check": "check_osc",
    },
    {
        "title": "初回起動",
        "description": (
            "全ての設定が完了しました！\n"
            "python -m osc_tracking.main でトラッキングを開始できます。"
        ),
        "check": None,
    },
]


def check_cameras() -> tuple[bool, str]:
    """Check if at least 2 cameras are available."""
    try:
        import cv2
    except ImportError:
        return False, "opencv-pythonがインストールされていません"

    available = []
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            available.append(i)
            cap.release()
        else:
            cap.release()

    if len(available) >= 2:
        return True, f"カメラ {len(available)} 台検出: {available}"
    elif len(available) == 1:
        return False, f"カメラ 1 台のみ検出 (インデックス {available[0]})。2台必要です"
    else:
        return False, "カメラが検出されません。接続を確認してください"


def check_model() -> tuple[bool, str]:
    """Check if MediaPipe model exists."""
    model_path = Path("models/pose_landmarker_heavy.task")
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        return True, f"モデル検出済み ({size_mb:.1f} MB)"
    return False, "モデルが見つかりません。ダウンロードします..."


def check_calibration() -> tuple[bool, str]:
    """Check if stereo calibration file exists."""
    calib_path = Path("calibration_data/stereo_calib.npz")
    if calib_path.exists():
        return True, "キャリブレーションファイル検出済み"
    return False, "キャリブレーション未実行。calibrateツールを実行してください"


def check_osc() -> tuple[bool, str]:
    """Check OSC connectivity."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "osc_tracking.tools.connection_check", "--timeout", "3"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return True, "OSC接続確認済み"
        return False, "OSCデータを受信できません。SlimeVR Serverが起動しているか確認してください"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "接続チェックがタイムアウトしました"


CHECKS = {
    "check_cameras": check_cameras,
    "check_model": check_model,
    "check_calibration": check_calibration,
    "check_osc": check_osc,
}


def run_wizard() -> None:
    """Run the interactive setup wizard."""
    print("=" * 60)
    print("  OSC Tracking セットアップウィザード")
    print("  7ステップで初期設定を完了します")
    print("=" * 60)
    print()

    for i, step in enumerate(STEPS, 1):
        print(f"--- ステップ {i}/{len(STEPS)}: {step['title']} ---")
        print(step["description"])
        print()

        if step["check"]:
            check_fn = CHECKS[step["check"]]
            ok, msg = check_fn()
            if ok:
                print(f"  [OK] {msg}")
            else:
                print(f"  [!!] {msg}")

                # Auto-fix for model download
                if step["check"] == "check_model":
                    print("  ダウンロード中...")
                    try:
                        subprocess.run(
                            [sys.executable, "-m", "osc_tracking.tools.download_model"],
                            check=True,
                        )
                        ok, msg = check_fn()
                        if ok:
                            print(f"  [OK] {msg}")
                    except subprocess.CalledProcessError:
                        print("  [!!] ダウンロード失敗")

                if not ok and step["check"] != "check_osc":
                    print()
                    resp = input("  続行しますか？ [y/N]: ").strip().lower()
                    if resp != "y":
                        print("\nセットアップを中断しました。")
                        return
        else:
            input("  Enterキーで次へ...")

        print()

    print("=" * 60)
    print("  セットアップ完了！")
    print("  python -m osc_tracking.main で起動してください")
    print("=" * 60)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_wizard()


if __name__ == "__main__":
    main()
