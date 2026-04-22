"""Configuration management for OSC Tracking.

Loads settings from config/default.yaml, overridable by user config
or command-line arguments.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

logger = logging.getLogger(__name__)


def _default_config_path() -> Path:
    return paths.default_config_path()


def _user_config_path() -> Path:
    return paths.user_config_path()


# Back-compat module-level aliases (resolved lazily at import time).
# Prefer paths.default_config_path() / paths.user_config_path() in new code.
CONFIG_DIR = paths.config_dir()
DEFAULT_CONFIG = _default_config_path()
USER_CONFIG = _user_config_path()


@dataclass
class TrackingConfig:
    """Complete configuration for the tracking system."""

    # Camera settings
    cam1_index: int = 0
    cam2_index: int = 1
    camera_resolution: tuple[int, int] = (640, 480)
    target_fps: int = 30

    # IMU receiver selector ("osc" or "ble"). Defaults to "osc" for
    # backward compatibility with existing SlimeTora/SlimeVR setups.
    receiver_type: str = "osc"

    # OSC settings (SlimeTora → SlimeVR Server → OSC)
    osc_receive_host: str = "127.0.0.1"
    osc_receive_port: int = 6969
    osc_send_host: str = "127.0.0.1"
    osc_send_port: int = 9000

    # BLE settings (direct HaritoraX2 connection — experimental).
    # Only used when receiver_type == "ble". ble_local_name_to_bone maps
    # each tracker peripheral's advertised name (discovered via the
    # `ble_scan` tool) to the skeleton bone it represents.
    ble_device_name_prefix: str = "HaritoraX2-"
    ble_scan_timeout_sec: float = 10.0
    ble_local_name_to_bone: dict[str, str] = field(default_factory=dict)

    # Calibration
    calibration_file: str = "calibration_data/stereo_calib.npz"

    # MediaPipe
    model_path: str = "models/pose_landmarker_heavy.task"
    model_path_lite: str = "models/pose_landmarker_lite.task"
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    # State machine thresholds
    visible_threshold: float = 0.7
    partial_threshold: float = 0.3
    osc_timeout_sec: float = 1.0
    hysteresis_sec: float = 0.5

    # Complementary filter
    smooth_rate: float = 5.0
    drift_velocity_threshold: float = 0.02
    drift_hold_seconds: float = 10.0

    # Visual compass
    compass_blend_factor: float = 0.3

    # FUTON_MODE
    futon_pitch_threshold: float = 60.0
    futon_exit_threshold: float = 30.0
    futon_dwell_time_sec: float = 0.5
    futon_trigger_joint: str = "Chest"

    def save(self, path: Path | None = None) -> None:
        """Save config to JSON file."""
        path = path or _user_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for k, v in self.__dict__.items():
            if isinstance(v, tuple):
                data[k] = list(v)
            else:
                data[k] = v
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info("Config saved to %s", path)

    @classmethod
    def load(cls, path: Path | None = None) -> "TrackingConfig":
        """Load config from JSON file, falling back to defaults."""
        config = cls()

        default = _default_config_path()
        if default.exists():
            _apply_json(config, default)

        target = path if path is not None else _user_config_path()
        if target.exists():
            _apply_json(config, target)

        return config


def _apply_json(config: TrackingConfig, path: Path) -> None:
    """Apply JSON file values to config object, with type validation."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if not hasattr(config, key):
                # Usually a stale key after a config rename — surface it
                # so users notice their setting is being silently dropped.
                logger.warning(
                    "Config %s: unknown key '%s' — ignored", path, key
                )
                continue
            if key == "camera_resolution":
                value = tuple(value)
            # Validate type matches the default
            expected = type(getattr(config, key))
            if expected in (int, float) and isinstance(value, (int, float)):
                value = expected(value)  # int/float coercion
            elif not isinstance(value, expected):
                logger.warning(
                    "Config %s: '%s' expected %s, got %s — skipping",
                    path, key, expected.__name__, type(value).__name__,
                )
                continue
            setattr(config, key, value)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load config %s: %s", path, e)
