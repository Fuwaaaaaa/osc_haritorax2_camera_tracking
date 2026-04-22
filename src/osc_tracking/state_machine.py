"""6-mode state machine for tracking mode management.

State Machine Diagram:
                    ┌─────────────┐
        ┌──────────►│   Visible    │◄──────────┐
        │           │ Conf > 0.7   │           │
        │           └──────┬───────┘           │
        │                  │ Conf drops        │ Conf recovers
        │                  ▼                   │ + smooth resync
        │           ┌─────────────┐           │
        │           │   Partial    │───────────┤
        │           │ 0.3<Conf<0.7 │           │
        │           └──────┬───────┘           │
        │                  │ Conf < 0.3        │
        │                  ▼                   │
        │           ┌─────────────┐           │
        ├───────────│    Full      │───────────┘
        │           │  Occlusion   │
        │           └──────────────┘
        │
        │           ┌─────────────┐
        ├───────────│  IMU Disconn │  (OSC timeout > 1s)
        │           └─────────────┘
        │           ┌─────────────┐
        └───────────│ Single Cam   │  (one camera confidence low)
                    │  Degraded    │
                    └──────────────┘
"""

import time
from dataclasses import dataclass
from enum import Enum, auto


class TrackingMode(Enum):
    VISIBLE = auto()
    PARTIAL_OCCLUSION = auto()
    FULL_OCCLUSION = auto()
    IMU_DISCONNECTED = auto()
    SINGLE_CAM_DEGRADED = auto()
    FUTON_MODE = auto()


@dataclass
class ModeConfig:
    """Thresholds and timing for mode transitions."""
    visible_threshold: float = 0.7
    partial_threshold: float = 0.3
    osc_timeout_sec: float = 1.0
    hysteresis_sec: float = 0.5
    resync_duration_sec: float = 1.0
    futon_pitch_threshold: float = 60.0
    futon_exit_threshold: float = 30.0
    futon_dwell_time_sec: float = 0.5
    futon_trigger_joint: str = "Chest"


class TrackingStateMachine:
    """Manages transitions between tracking modes based on sensor confidence.

    Hysteresis prevents rapid mode switching: a mode must be stable for
    `hysteresis_sec` before transitioning.
    """

    def __init__(self, config: ModeConfig | None = None):
        self.config = config or ModeConfig()
        self.mode = TrackingMode.VISIBLE
        self._pending_mode: TrackingMode | None = None
        self._pending_since: float = 0.0
        self._last_osc_time: float = time.monotonic()
        self._resync_start: float | None = None
        self._futon_active: bool = False
        self._futon_pending_since: float | None = None
        self._futon_exit_pending_since: float | None = None

    @property
    def is_resyncing(self) -> bool:
        """True during the 1-second resync window after IMU reconnection."""
        if self._resync_start is None:
            return False
        elapsed = time.monotonic() - self._resync_start
        if elapsed >= self.config.resync_duration_sec:
            self._resync_start = None
            return False
        return True

    def on_imu_pitch(self, pitch_degrees: float) -> None:
        """Update futon mode based on chest IMU pitch angle.

        Args:
            pitch_degrees: Pitch angle in degrees. Uses YXZ euler convention.
        """
        import math
        if not math.isfinite(pitch_degrees):
            return

        now = time.monotonic()
        abs_pitch = abs(pitch_degrees)
        if abs_pitch >= self.config.futon_pitch_threshold:
            self._futon_exit_pending_since = None  # Cancel any pending exit
            if not self._futon_active:
                if self._futon_pending_since is None:
                    self._futon_pending_since = now
                elapsed = now - self._futon_pending_since
                if elapsed >= self.config.futon_dwell_time_sec:
                    self._futon_active = True
                    self._futon_pending_since = None
        elif abs_pitch < self.config.futon_exit_threshold:
            self._futon_pending_since = None  # Cancel any pending entry
            if self._futon_active:
                if self._futon_exit_pending_since is None:
                    self._futon_exit_pending_since = now
                elapsed = now - self._futon_exit_pending_since
                if elapsed >= self.config.futon_dwell_time_sec:
                    self._futon_active = False
                    self._futon_exit_pending_since = None
            # When not active, _futon_exit_pending_since is already None
            # (cleared on the active→inactive transition above).
        # In deadband (exit_threshold <= pitch < pitch_threshold): no change

    def on_imu_received(self) -> None:
        """Call when an OSC message is received from the IMU tracker."""
        was_disconnected = self.mode == TrackingMode.IMU_DISCONNECTED
        self._last_osc_time = time.monotonic()
        if was_disconnected:
            self._resync_start = time.monotonic()

    def update(
        self,
        cam1_confidence: float,
        cam2_confidence: float,
        now: float | None = None,
    ) -> TrackingMode:
        """Evaluate sensor state and return the current tracking mode.

        Args:
            cam1_confidence: MediaPipe visibility score for camera 1 (0.0-1.0)
            cam2_confidence: MediaPipe visibility score for camera 2 (0.0-1.0)
            now: Current time (monotonic). Defaults to time.monotonic().

        Returns:
            The active TrackingMode after evaluation.
        """
        if now is None:
            now = time.monotonic()

        # Check IMU connectivity first (highest priority)
        osc_elapsed = now - self._last_osc_time
        if osc_elapsed > self.config.osc_timeout_sec:
            self._apply_mode(TrackingMode.IMU_DISCONNECTED, now)
            return self.mode

        # Check FUTON_MODE (second priority — user lying down)
        if self._futon_active:
            self.mode = TrackingMode.FUTON_MODE
            self._pending_mode = None
            return self.mode

        # Weighted average confidence from both cameras
        avg_confidence = (cam1_confidence + cam2_confidence) / 2.0

        # Both cameras lost simultaneously — bypass hysteresis
        if cam1_confidence < 0.05 and cam2_confidence < 0.05:
            self.mode = TrackingMode.FULL_OCCLUSION
            self._pending_mode = None
            return self.mode

        # Check for single camera degradation
        cam_diff = abs(cam1_confidence - cam2_confidence)
        min_cam = min(cam1_confidence, cam2_confidence)
        if (
            cam_diff > 0.4
            and min_cam < self.config.partial_threshold
            and avg_confidence >= self.config.partial_threshold
        ):
            self._apply_mode(TrackingMode.SINGLE_CAM_DEGRADED, now)
            return self.mode

        # Standard confidence-based transitions
        if avg_confidence >= self.config.visible_threshold:
            target = TrackingMode.VISIBLE
        elif avg_confidence >= self.config.partial_threshold:
            target = TrackingMode.PARTIAL_OCCLUSION
        else:
            target = TrackingMode.FULL_OCCLUSION

        self._apply_mode(target, now)
        return self.mode

    def _apply_mode(self, target: TrackingMode, now: float) -> None:
        """Apply mode transition with hysteresis."""
        if target == self.mode:
            self._pending_mode = None
            return

        if target != self._pending_mode:
            self._pending_mode = target
            self._pending_since = now

        # Check if hysteresis period has elapsed (immediate if hysteresis_sec == 0)
        if now - self._pending_since >= self.config.hysteresis_sec:
            self.mode = target
            self._pending_mode = None
