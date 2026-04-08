"""Motion smoothing presets — different feel for different activities.

Each preset adjusts the complementary filter's smoothing parameters
to change how movement feels.
"""

from dataclasses import dataclass


@dataclass
class SmoothingPreset:
    """Parameters that control motion feel."""
    name: str
    smooth_rate: float       # Exponential decay rate (higher = snappier)
    noise_threshold: float   # Below this velocity, suppress drift
    prediction_weight: float  # How much to trust velocity prediction (0-1)
    description: str = ""


PRESETS = {
    "default": SmoothingPreset(
        name="Default",
        smooth_rate=5.0,
        noise_threshold=0.02,
        prediction_weight=0.3,
        description="Balanced for general use",
    ),
    "anime": SmoothingPreset(
        name="Anime",
        smooth_rate=8.0,
        noise_threshold=0.03,
        prediction_weight=0.5,
        description="Snappy, responsive — good for expressive avatars",
    ),
    "realistic": SmoothingPreset(
        name="Realistic",
        smooth_rate=3.0,
        noise_threshold=0.01,
        prediction_weight=0.2,
        description="Smooth, natural — good for mocap recording",
    ),
    "dance": SmoothingPreset(
        name="Dance",
        smooth_rate=10.0,
        noise_threshold=0.05,
        prediction_weight=0.6,
        description="Ultra-responsive — keeps up with fast moves",
    ),
    "sleep": SmoothingPreset(
        name="Sleep/Lying",
        smooth_rate=2.0,
        noise_threshold=0.005,
        prediction_weight=0.1,
        description="Very smooth — minimal jitter for bed/futon use",
    ),
}


def get_preset(name: str) -> SmoothingPreset:
    """Get a smoothing preset by name."""
    return PRESETS.get(name, PRESETS["default"])


def list_presets() -> list[str]:
    """List available preset names."""
    return list(PRESETS.keys())
