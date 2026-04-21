"""Startup preflight checks for the OSC Tracking main process.

Runs before any subsystem is constructed and surfaces actionable Japanese
error messages for the most common first-run failures (missing model,
missing stereo calibration, occupied OSC port). Errors abort startup
with a clear fix; warnings print and continue.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .config import TrackingConfig

logger = logging.getLogger(__name__)

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class PreflightIssue:
    severity: Severity
    code: str
    message: str  # Japanese, shown to the user
    fix: str | None = None  # concrete command or path

    @staticmethod
    def has_errors(issues: list["PreflightIssue"]) -> bool:
        return any(i.severity == "error" for i in issues)

    def format(self) -> str:
        tag = "エラー" if self.severity == "error" else "警告"
        parts = [f"[{tag}] {self.message}"]
        if self.fix:
            parts.append(f"  対処: {self.fix}")
        return "\n".join(parts)


def check_model_file(model_path: str, model_path_lite: str) -> list[PreflightIssue]:
    """MediaPipe needs at least one model file present."""
    if Path(model_path).exists() or Path(model_path_lite).exists():
        return []
    return [
        PreflightIssue(
            severity="error",
            code="missing_model",
            message=(
                f"MediaPipeモデルが見つかりません: "
                f"{model_path} / {model_path_lite}"
            ),
            fix=(
                "osc_tools.exe download_model "
                "(または python -m osc_tracking.tools.download_model)"
                " を実行してください"
            ),
        )
    ]


def check_calibration_file(calibration_file: str) -> list[PreflightIssue]:
    """Missing calibration is survivable — we fall back to monocular depth —
    but warn because accuracy drops significantly."""
    if Path(calibration_file).exists():
        return []
    return [
        PreflightIssue(
            severity="warning",
            code="missing_calibration",
            message=(
                f"ステレオキャリブレーションが見つかりません: {calibration_file}"
                " (単眼フォールバックで起動します)"
            ),
            fix=(
                "osc_tools.exe calibrate "
                "(または python -m osc_tracking.tools.calibrate)"
                " で初回キャリブレーションを実行してください"
            ),
        )
    ]


def check_osc_port(host: str, port: int) -> list[PreflightIssue]:
    """Fail fast if the OSC receive port is already bound.

    A port=0 request asks the OS for any free port, so it can never fail —
    treat that case as always-OK.
    """
    if port == 0:
        return []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((host, port))
    except OSError as e:
        return [
            PreflightIssue(
                severity="error",
                code="port_in_use",
                message=(
                    f"OSC受信ポート {host}:{port} を開けませんでした ({e})"
                ),
                fix=(
                    "SlimeVR Server などが同じポートを使用していないか確認し、"
                    "--osc-port で別のポートを指定してください"
                ),
            )
        ]
    finally:
        sock.close()
    return []


def run_preflight_checks(
    cfg: TrackingConfig, *, no_camera: bool = False
) -> list[PreflightIssue]:
    """Aggregate all checks. Camera-specific checks are skipped in --no-camera mode."""
    issues: list[PreflightIssue] = []
    if not no_camera:
        issues.extend(check_model_file(cfg.model_path, cfg.model_path_lite))
        issues.extend(check_calibration_file(cfg.calibration_file))
    issues.extend(check_osc_port(cfg.osc_receive_host, cfg.osc_receive_port))
    return issues
