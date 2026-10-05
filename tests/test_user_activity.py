"""
user_activity モジュールのテスト
ioreg の出力から操作なし時間を読み取れるかを検証する。
"""

import subprocess
from unittest.mock import MagicMock, patch

from user_activity import get_idle_seconds


class TestGetIdleSeconds:
    """操作なし時間の取得のテスト"""

    @patch("user_activity.subprocess.run")
    def test_converts_nanoseconds_to_seconds(self, run):
        run.return_value = MagicMock(
            stdout='    | |     "HIDIdleTime" = 17636449291\n'
        )

        assert get_idle_seconds() == 17.636449291

    @patch("user_activity.subprocess.run")
    def test_returns_none_when_key_missing(self, run):
        run.return_value = MagicMock(stdout="no such key\n")

        assert get_idle_seconds() is None

    @patch("user_activity.subprocess.run")
    def test_returns_none_when_ioreg_fails(self, run):
        run.side_effect = subprocess.CalledProcessError(1, "ioreg")

        assert get_idle_seconds() is None
