"""Configuration management for OSC Tracking.

Loads settings from config/default.yaml, overridable by user config
or command-line arguments.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path("config")
DEFAULT_CONFIG = CONFIG_DIR / "default.json"
USER_CONFIG = CONFIG_DIR / "user.json"


@dataclass
class TrackingConfig:
    """Complete configuration for the tracking system."""

    # Camera settings
    cam1_index: int = 0
    cam2_index: int = 1
    camera_resolution: tuple[int, int] = (640, 480)
    target_fps: int = 30

    # OSC settings (SlimeTora → SlimeVR Server → OSC)
    osc_receive_host: str = "127.0.0.1"
    osc_receive_port: int = 6969
    osc_send_host: str = "127.0.0.1"
    osc_send_port: int = 9000

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
        path = path or USER_CONFIG
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

        # Load default config
        if DEFAULT_CONFIG.exists():
            _apply_json(config, DEFAULT_CONFIG)

        # Override with user config
        target = path or USER_CONFIG
        if target.exists():
            _apply_json(config, target)

        return config


def _apply_json(config: TrackingConfig, path: Path) -> None:
    """Apply JSON file values to config object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in data.items():
            if hasattr(config, key):
                if key == "camera_resolution":
                    value = tuple(value)
                setattr(config, key, value)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load config %s: %s", path, e)
