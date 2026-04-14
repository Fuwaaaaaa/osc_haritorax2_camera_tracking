"""Tests for configuration management."""


from osc_tracking.config import TrackingConfig


class TestDefaults:
    def test_default_values(self):
        cfg = TrackingConfig()
        assert cfg.cam1_index == 0
        assert cfg.target_fps == 30
        assert cfg.visible_threshold == 0.7
        assert cfg.osc_receive_port == 6969
        assert cfg.osc_send_port == 9000

    def test_camera_resolution_is_tuple(self):
        cfg = TrackingConfig()
        assert isinstance(cfg.camera_resolution, tuple)
        assert cfg.camera_resolution == (640, 480)


class TestSaveLoad:
    def test_round_trip(self, tmp_path):
        cfg = TrackingConfig()
        cfg.cam1_index = 2
        cfg.target_fps = 60
        cfg.visible_threshold = 0.8

        path = tmp_path / "test_config.json"
        cfg.save(path)

        loaded = TrackingConfig.load(path)
        assert loaded.cam1_index == 2
        assert loaded.target_fps == 60
        assert loaded.visible_threshold == 0.8

    def test_save_creates_directory(self, tmp_path):
        cfg = TrackingConfig()
        path = tmp_path / "subdir" / "config.json"
        cfg.save(path)
        assert path.exists()

    def test_load_nonexistent_returns_defaults(self, tmp_path):
        cfg = TrackingConfig.load(tmp_path / "nonexistent.json")
        assert cfg.cam1_index == 0  # Default

    def test_camera_resolution_preserved_as_tuple(self, tmp_path):
        cfg = TrackingConfig()
        cfg.camera_resolution = (1280, 720)
        path = tmp_path / "res_test.json"
        cfg.save(path)

        loaded = TrackingConfig.load(path)
        assert loaded.camera_resolution == (1280, 720)
        assert isinstance(loaded.camera_resolution, tuple)

    def test_invalid_json_returns_defaults(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        cfg = TrackingConfig.load(path)
        assert cfg.cam1_index == 0


class TestTypeValidation:
    """Config load rejects wrong types and coerces int/float."""

    def test_string_for_float_rejected(self, tmp_path):
        """String value for a float field should be skipped."""
        path = tmp_path / "bad_type.json"
        path.write_text('{"visible_threshold": "high"}')
        cfg = TrackingConfig.load(path)
        assert cfg.visible_threshold == 0.7  # Default kept

    def test_string_for_int_rejected(self, tmp_path):
        path = tmp_path / "bad_type.json"
        path.write_text('{"cam1_index": "zero"}')
        cfg = TrackingConfig.load(path)
        assert cfg.cam1_index == 0

    def test_int_coerced_to_float(self, tmp_path):
        """JSON integer for a float field should be coerced."""
        path = tmp_path / "coerce.json"
        path.write_text('{"visible_threshold": 1}')
        cfg = TrackingConfig.load(path)
        assert cfg.visible_threshold == 1.0
        assert isinstance(cfg.visible_threshold, float)

    def test_float_coerced_to_int(self, tmp_path):
        """JSON float for an int field should be coerced."""
        path = tmp_path / "coerce.json"
        path.write_text('{"target_fps": 60.0}')
        cfg = TrackingConfig.load(path)
        assert cfg.target_fps == 60
        assert isinstance(cfg.target_fps, int)

    def test_unknown_key_ignored(self, tmp_path):
        path = tmp_path / "extra.json"
        path.write_text('{"nonexistent_key": 42, "cam1_index": 3}')
        cfg = TrackingConfig.load(path)
        assert cfg.cam1_index == 3
        assert not hasattr(cfg, "nonexistent_key")
