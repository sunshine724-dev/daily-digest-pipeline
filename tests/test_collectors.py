"""
収集モジュールのユニットテスト
外部依存をモックして各コレクタのロジックをテストする。
"""

from unittest.mock import patch, MagicMock
from datetime import datetime, timezone


class TestNotionCollector:
    """Notion収集モジュールのテスト"""

    @patch("collectors.notion_collector.Client")
    def test_collect_returns_pages(self, mock_client_cls):
        """今日編集されたページが正しく返されること"""
        import config
        config.NOTION_API_TOKEN = "test-token"

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.search.return_value = {
            "results": [
                {
                    "last_edited_time": f"{today_str}T12:00:00.000Z",
                    "url": "https://notion.so/test-page",
                    "properties": {
                        "title": {
                            "type": "title",
                            "title": [{"plain_text": "テストページ"}],
                        }
                    },
                }
            ],
            "has_more": False,
        }

        from collectors import notion_collector
        result = notion_collector.collect()

        assert len(result) == 1
        assert result[0]["title"] == "テストページ"
        assert result[0]["url"] == "https://notion.so/test-page"

    @patch("collectors.notion_collector.Client")
    def test_collect_empty_when_no_token(self, mock_client_cls):
        """トークン未設定時は空リストを返すこと"""
        import config
        config.NOTION_API_TOKEN = ""

        from collectors import notion_collector
        result = notion_collector.collect()

        assert result == []
        mock_client_cls.assert_not_called()


class TestGitHubCollector:
    """GitHub収集モジュールのテスト"""

    @patch("collectors.github_collector.Github")
    def test_collect_returns_activities(self, mock_github_cls):
        """今日のPushイベントが正しく集計されること"""
        import config
        config.GITHUB_TOKEN = "test-token"
        config.GITHUB_USERNAME = "testuser"

        now = datetime.now(timezone.utc)

        mock_github = MagicMock()
        mock_github_cls.return_value = mock_github
        mock_user = MagicMock()
        mock_github.get_user.return_value = mock_user

        # PushEventイベントを作成
        mock_event = MagicMock()
        mock_event.type = "PushEvent"
        mock_event.created_at = now
        mock_event.repo.name = "testuser/test-repo"
        mock_event.payload = {
            "commits": [
                {"message": "feat: テスト機能追加"},
                {"message": "fix: バグ修正"},
            ]
        }

        # 古いイベント（ループ終了用）
        mock_old_event = MagicMock()
        mock_old_event.type = "PushEvent"
        mock_old_event.created_at = datetime(2020, 1, 1, tzinfo=timezone.utc)

        mock_user.get_events.return_value = [mock_event, mock_old_event]

        from collectors import github_collector
        result = github_collector.collect()

        assert len(result) == 1
        assert result[0]["repo_name"] == "testuser/test-repo"
        assert result[0]["commits"] == 2
        assert "feat: テスト機能追加" in result[0]["commit_messages"]

    @patch("collectors.github_collector.Github")
    def test_collect_empty_when_no_token(self, mock_github_cls):
        """トークン未設定時は空リストを返すこと"""
        import config
        config.GITHUB_TOKEN = ""

        from collectors import github_collector
        result = github_collector.collect()

        assert result == []


class TestChromeCollector:
    """Chrome収集モジュールのテスト"""

    @patch("collectors.chrome_collector.shutil")
    @patch("collectors.chrome_collector.sqlite3")
    def test_collect_returns_sites(self, mock_sqlite3, mock_shutil):
        """Chrome履歴が正しく取得されること"""
        import config
        from pathlib import Path

        # 存在するパスをモック
        config.CHROME_HISTORY_PATH = Path(__file__).parent / "fake_history"
        with patch.object(Path, "exists", return_value=True):
            mock_conn = MagicMock()
            mock_sqlite3.connect.return_value = mock_conn
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor

            mock_cursor.fetchall.return_value = [
                ("https://github.com", "GitHub", 10),
                ("https://stackoverflow.com", "Stack Overflow", 5),
            ]

            from collectors import chrome_collector
            result = chrome_collector.collect()

            assert len(result) == 2
            assert result[0]["title"] == "GitHub"
            assert result[0]["visit_count"] == 10


class TestActivityWatchCollector:
    """ActivityWatch収集モジュールのテスト"""

    @patch("collectors.activitywatch_collector.requests")
    def test_collect_returns_app_times(self, mock_requests):
        """アプリ別時間が正しく集計されること"""
        # バケット一覧のモック
        mock_buckets_resp = MagicMock()
        mock_buckets_resp.json.return_value = {
            "aw-watcher-window_test": {"type": "currentwindow"}
        }

        # イベントのモック
        mock_events_resp = MagicMock()
        mock_events_resp.json.return_value = [
            {"data": {"app": "Code.exe"}, "duration": 3600},
            {"data": {"app": "Code.exe"}, "duration": 1800},
            {"data": {"app": "chrome.exe"}, "duration": 900},
        ]

        mock_requests.get.side_effect = [mock_buckets_resp, mock_events_resp]

        from collectors import activitywatch_collector
        result = activitywatch_collector.collect()

        assert len(result) == 2
        # Code.exe の合計は 5400秒
        code_entry = next(e for e in result if e["app_name"] == "Code.exe")
        assert code_entry["duration_seconds"] == 5400
