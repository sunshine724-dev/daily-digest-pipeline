"""
config モジュールのテスト
端末名と収集対象の既定値を検証する。
"""

import config


class TestDeviceDefaults:
    """端末ごとの既定値のテスト"""

    def test_mac_platform_is_mac(self):
        assert config.default_device_name("darwin") == "Mac"

    def test_windows_platform_is_win(self):
        assert config.default_device_name("win32") == "Win"

    def test_mac_collects_only_pc_local_sources(self):
        assert config.default_collectors("Mac") == ("activitywatch", "whatpulse")

    def test_win_collects_everything(self):
        assert config.default_collectors("Win") == config.ALL_COLLECTORS


class TestParseCollectors:
    """COLLECTORS の解釈のテスト"""

    def test_strips_spaces_and_empty_items(self):
        assert config.parse_collectors(" activitywatch, ,whatpulse ") == (
            "activitywatch",
            "whatpulse",
        )

    def test_empty_string_is_empty(self):
        assert config.parse_collectors("") == ()
