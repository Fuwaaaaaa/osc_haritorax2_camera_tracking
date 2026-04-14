"""Setup wizard — guided first-time configuration for OSC Tracking.

Walks the user through 7 steps to get from zero to tracking:
1. MediaPipeモデルダウンロード
2. カメラ確認
3. SlimeTora + SlimeVR Server接続
4. OSCポート確認
5. ステレオキャリブレーション
6. テスト起動
7. 設定保存

Usage:
    python -m osc_tracking.tools.setup_wizard
"""

import argparse
import logging
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


@dataclass
class CameraCheckResult:
    """Result of camera availability check."""
    cam1_ok: bool
    cam2_ok: bool


@dataclass
class WizardStep:
    """Definition of a single wizard step."""
    number: int
    title: str
    description: str
    auto: bool = False  # True if step runs automatically without user action


WIZARD_STEPS = [
    WizardStep(
        number=1,
        title="MediaPipeモデルダウンロード",
        description="ポーズ推定に必要なMediaPipe Pose Landmarkerモデルをダウンロードします。",
        auto=True,
    ),
    WizardStep(
        number=2,
        title="カメラ確認",
        description="2台のWebカメラが接続されているか確認します。",
        auto=True,
    ),
    WizardStep(
        number=3,
        title="SlimeTora + SlimeVR Server接続",
        description=(
            "HaritoraX2のIMUデータを受信するために、SlimeToraとSlimeVR Serverが"
            "起動していることを確認します。"
        ),
    ),
    WizardStep(
        number=4,
        title="OSCポート確認",
        description="OSC通信に使うポート（受信: 6969、送信: 9000）が使用可能か確認します。",
        auto=True,
    ),
    WizardStep(
        number=5,
        title="ステレオキャリブレーション",
        description=(
            "2台のカメラの位置関係を測定します。チェッカーボードパターンを使って"
            "キャリブレーションを行います。"
        ),
    ),
    WizardStep(
        number=6,
        title="テスト起動",
        description="全コンポーネントを起動して動作確認します。カメラプレビューで骨格が表示されるか確認してください。",
    ),
    WizardStep(
        number=7,
        title="設定保存",
        description="設定をconfig/user.jsonに保存します。次回からは python -m osc_tracking.main で起動できます。",
        auto=True,
    ),
]


def check_cameras(cam1_index: int = 0, cam2_index: int = 1) -> CameraCheckResult:
    """Check if both cameras are available.

    Returns:
        CameraCheckResult with per-camera status.
    """
    import cv2

    results = {}
    for label, idx in [("cam1", cam1_index), ("cam2", cam2_index)]:
        cap = cv2.VideoCapture(idx)
        try:
            ok = False
            if cap.isOpened():
                ret, _ = cap.read()
                ok = ret
        finally:
            cap.release()
        results[label] = ok

    return CameraCheckResult(cam1_ok=results["cam1"], cam2_ok=results["cam2"])


def check_mediapipe_model(model_path: str) -> bool:
    """Check if the MediaPipe model file exists."""
    return Path(model_path).exists()


def check_osc_port_available(port: int) -> bool:
    """Check if a UDP port is available for binding."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _print_header() -> None:
    print(f"\n{CYAN}{'=' * 55}")
    print(f"  OSC Tracking セットアップウィザード")
    print(f"  HaritoraX2 + デュアルWebカメラ")
    print(f"{'=' * 55}{RESET}\n")
    print("  初回セットアップを7ステップでガイドします。")
    print("  各ステップで必要なものが揃っているか確認します。\n")


def _print_step(step: WizardStep, status: str = "") -> None:
    status_icon = {
        "": f"{DIM}[ ]{RESET}",
        "ok": f"{GREEN}[✓]{RESET}",
        "warn": f"{YELLOW}[!]{RESET}",
        "fail": f"{RED}[✗]{RESET}",
        "skip": f"{DIM}[-]{RESET}",
    }.get(status, f"{DIM}[ ]{RESET}")

    print(f"  {status_icon} {BOLD}Step {step.number}: {step.title}{RESET}")
    if status == "":
        print(f"      {DIM}{step.description}{RESET}")


def _wait_for_enter(prompt: str = "  Enterで続行...") -> None:
    try:
        input(prompt)
    except (EOFError, KeyboardInterrupt):
        print(f"\n  {YELLOW}中断されました。{RESET}")
        sys.exit(0)


def _run_step_1_model(model_path: str) -> bool:
    """Step 1: Check/download MediaPipe model."""
    if check_mediapipe_model(model_path):
        print(f"      {GREEN}モデル検出: {model_path}{RESET}")
        return True

    print(f"      {YELLOW}モデルが見つかりません: {model_path}{RESET}")
    print(f"      ダウンロードを実行します...")
    try:
        subprocess.run(
            [sys.executable, "-m", "osc_tracking.tools.download_model"],
            check=True,
            timeout=120,
        )
        if check_mediapipe_model(model_path):
            print(f"      {GREEN}ダウンロード完了{RESET}")
            return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"      {RED}ダウンロード失敗: {e}{RESET}")
    return False


def _run_step_2_cameras(cam1: int, cam2: int) -> bool:
    """Step 2: Check camera availability."""
    result = check_cameras(cam1, cam2)
    if result.cam1_ok and result.cam2_ok:
        print(f"      {GREEN}カメラ1 (index {cam1}): OK{RESET}")
        print(f"      {GREEN}カメラ2 (index {cam2}): OK{RESET}")
        return True
    if not result.cam1_ok:
        print(f"      {RED}カメラ1 (index {cam1}): 検出できません{RESET}")
    else:
        print(f"      {GREEN}カメラ1 (index {cam1}): OK{RESET}")
    if not result.cam2_ok:
        print(f"      {RED}カメラ2 (index {cam2}): 検出できません{RESET}")
    else:
        print(f"      {GREEN}カメラ2 (index {cam2}): OK{RESET}")

    print(f"\n      {YELLOW}ヒント: --cam1 / --cam2 でカメラ番号を変更できます{RESET}")
    return False


def _run_step_3_slimevr() -> bool:
    """Step 3: Guide user to set up SlimeTora + SlimeVR."""
    print(f"\n      {BOLD}必要なソフトウェア:{RESET}")
    print(f"      1. SlimeTora — HaritoraX2をSlimeVRに接続")
    print(f"         https://github.com/OCSYT/SlimeTora")
    print(f"      2. SlimeVR Server — OSCでデータを出力")
    print(f"         https://slimevr.dev/download")
    print()
    print(f"      {BOLD}手順:{RESET}")
    print(f"      1. HaritoraX2の電源を入れる")
    print(f"      2. SlimeToraを起動し、トラッカーが接続されるのを確認")
    print(f"      3. SlimeVR Serverを起動")
    print(f"      4. SlimeVR Serverの設定でOSC出力を有効化（ポート6969）")
    print()
    _wait_for_enter("  準備ができたらEnterで続行...")

    print(f"      OSC接続を確認中（10秒間）...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "osc_tracking.tools.connection_check",
             "--port", "6969", "--duration", "10"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if "HEALTH: GOOD" in result.stdout:
            print(f"      {GREEN}SlimeVR OSC接続: OK{RESET}")
            return True
        elif "HEALTH: PARTIAL" in result.stdout:
            print(f"      {YELLOW}一部のトラッカーのみ検出{RESET}")
            return True
        else:
            print(f"      {RED}OSCメッセージが受信できません{RESET}")
            print(f"      SlimeVR ServerのOSC設定を確認してください")
            return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f"      {RED}接続チェックがタイムアウトしました{RESET}")
        return False


def _run_step_4_ports(receive_port: int, send_port: int) -> bool:
    """Step 4: Check OSC port availability."""
    recv_ok = check_osc_port_available(receive_port)
    send_ok = check_osc_port_available(send_port)

    if recv_ok:
        print(f"      {GREEN}受信ポート {receive_port}: 利用可能{RESET}")
    else:
        print(f"      {RED}受信ポート {receive_port}: 使用中{RESET}")
        print(f"      SlimeVR Serverが既に使用している可能性があります（正常）")
        recv_ok = True  # Expected if SlimeVR is running

    if send_ok:
        print(f"      {GREEN}送信ポート {send_port}: 利用可能{RESET}")
    else:
        print(f"      {YELLOW}送信ポート {send_port}: 使用中（VRChatが起動中？）{RESET}")

    return recv_ok


def _run_step_5_calibration(cam1: int, cam2: int) -> bool:
    """Step 5: Run stereo calibration."""
    calib_path = Path("calibration_data/stereo_calib.npz")
    if calib_path.exists():
        print(f"      {GREEN}キャリブレーションデータ検出: {calib_path}{RESET}")
        _wait_for_enter("  既存のデータを使う場合はEnter、やり直す場合は 'r' + Enter: ")
        # For simplicity, always use existing if found
        return True

    print(f"\n      {BOLD}ステレオキャリブレーション手順:{RESET}")
    print(f"      1. チェッカーボードを印刷（9×6、25mm正方形）")
    print(f"         生成: python -m osc_tracking.tools.generate_checkerboard")
    print(f"      2. 両カメラに映る位置でボードを持つ")
    print(f"      3. SPACEで撮影（10枚以上、角度を変えて）")
    print(f"      4. 'c'でキャリブレーション実行、'q'で終了")
    print()
    _wait_for_enter("  Enterでキャリブレーションツールを起動...")

    try:
        subprocess.run(
            [sys.executable, "-m", "osc_tracking.tools.calibrate",
             "--cam1", str(cam1), "--cam2", str(cam2)],
            timeout=300,
        )
        return calib_path.exists()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        print(f"      {RED}キャリブレーションが中断されました{RESET}")
        return False


def _run_step_6_test(cam1: int, cam2: int) -> bool:
    """Step 6: Test preview with skeleton overlay."""
    print(f"\n      カメラプレビューを起動します。")
    print(f"      骨格が表示されれば成功です。'q'で閉じてください。")
    print()
    _wait_for_enter("  Enterでプレビューを起動...")

    try:
        subprocess.run(
            [sys.executable, "-m", "osc_tracking.tools.preview",
             "--cam1", str(cam1), "--cam2", str(cam2)],
            timeout=120,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def _run_step_7_save(cam1: int, cam2: int) -> bool:
    """Step 7: Save configuration."""
    from osc_tracking.config import TrackingConfig

    cfg = TrackingConfig()
    cfg.cam1_index = cam1
    cfg.cam2_index = cam2
    cfg.save()
    print(f"      {GREEN}設定を保存しました: config/user.json{RESET}")
    return True


def run_wizard(cam1: int = 0, cam2: int = 1) -> None:
    """Run the full setup wizard."""
    _print_header()

    model_path = "models/pose_landmarker_heavy.task"
    results: dict[int, bool] = {}

    for step in WIZARD_STEPS:
        print()
        _print_step(step)
        print()

        if step.number == 1:
            ok = _run_step_1_model(model_path)
        elif step.number == 2:
            ok = _run_step_2_cameras(cam1, cam2)
        elif step.number == 3:
            ok = _run_step_3_slimevr()
        elif step.number == 4:
            ok = _run_step_4_ports(6969, 9000)
        elif step.number == 5:
            ok = _run_step_5_calibration(cam1, cam2)
        elif step.number == 6:
            ok = _run_step_6_test(cam1, cam2)
        elif step.number == 7:
            ok = _run_step_7_save(cam1, cam2)
        else:
            ok = False

        results[step.number] = ok
        status = "ok" if ok else "fail"
        _print_step(step, status)

        if not ok and step.number <= 2:
            print(f"\n      {YELLOW}このステップは必須です。問題を解決してから再実行してください。{RESET}")
            _wait_for_enter("  スキップして続行する場合はEnter...")

    # Summary
    print(f"\n{CYAN}{'=' * 55}")
    print(f"  セットアップ完了")
    print(f"{'=' * 55}{RESET}\n")

    passed = sum(1 for ok in results.values() if ok)
    total = len(results)
    print(f"  結果: {passed}/{total} ステップ成功\n")

    for step in WIZARD_STEPS:
        ok = results.get(step.number, False)
        _print_step(step, "ok" if ok else "fail")

    if passed == total:
        print(f"\n  {GREEN}{BOLD}セットアップ完了！{RESET}")
        print(f"  起動: python -m osc_tracking.main")
        print(f"  ダッシュボード: http://localhost:8765\n")
    else:
        print(f"\n  {YELLOW}一部のステップが未完了です。{RESET}")
        print(f"  再実行: python -m osc_tracking.tools.setup_wizard\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OSC Tracking セットアップウィザード"
    )
    parser.add_argument("--cam1", type=int, default=0, help="Camera 1 index")
    parser.add_argument("--cam2", type=int, default=1, help="Camera 2 index")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    run_wizard(cam1=args.cam1, cam2=args.cam2)


if __name__ == "__main__":
    main()
