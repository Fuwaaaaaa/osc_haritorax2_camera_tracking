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
