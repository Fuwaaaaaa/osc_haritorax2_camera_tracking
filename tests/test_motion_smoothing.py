"""Tests for motion smoothing presets."""

import pytest

from osc_tracking.motion_smoothing import (
    PRESETS,
    SmoothingPreset,
    get_preset,
    list_presets,
)


class TestPresets:
    def test_all_preset_names_listed(self):
        names = set(list_presets())
        assert names == {"default", "anime", "realistic", "dance", "sleep"}

    def test_each_preset_has_valid_parameters(self):
        """All presets must have positive rates and thresholds, and a
        prediction_weight in [0, 1]."""
        for name, p in PRESETS.items():
            assert p.smooth_rate > 0, name
            assert p.noise_threshold > 0, name
            assert 0.0 <= p.prediction_weight <= 1.0, name
            assert p.name, name
            assert p.description, name


class TestGetPreset:
    def test_known_name_returns_preset(self):
        preset = get_preset("anime")
        assert preset.name == "Anime"
        assert preset.smooth_rate == pytest.approx(8.0)

    def test_unknown_name_falls_back_to_default(self):
        """Silent fallback — the CLI layer validates choices, but safety
        net must still keep a sensible preset."""
        preset = get_preset("nonsense")
        assert preset is PRESETS["default"]

    @pytest.mark.parametrize("name", ["default", "anime", "realistic", "dance", "sleep"])
    def test_every_name_resolvable(self, name):
        preset = get_preset(name)
        assert isinstance(preset, SmoothingPreset)


class TestOrdering:
    """Sanity checks on relative parameter ordering — catches accidental swaps."""

    def test_dance_is_more_responsive_than_realistic(self):
        assert PRESETS["dance"].smooth_rate > PRESETS["realistic"].smooth_rate

    def test_sleep_has_lowest_noise_threshold(self):
        thresholds = {n: p.noise_threshold for n, p in PRESETS.items()}
        assert thresholds["sleep"] == min(thresholds.values())
