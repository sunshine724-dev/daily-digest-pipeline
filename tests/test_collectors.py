"""
収集モジュールのユニットテスト
外部依存をモックして各コレクタのロジックをテストする。
"""

from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone


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

        assert len(result["app_times"]) == 2
        # Code.exe の合計は 5400秒
        code_entry = next(e for e in result["app_times"] if e["app_name"] == "Code.exe")
        assert code_entry["duration_seconds"] == 5400
        # timestamp の無いイベントは時間帯に振り分けられない
        assert result["timeline"] == []

    @patch("collectors.activitywatch_collector.requests")
    def test_collect_uses_jst_day_boundaries(self, mock_requests):
        """対象日を JST の 0:00〜24:00 で区切ること"""
        mock_buckets_resp = MagicMock()
        mock_buckets_resp.json.return_value = {
            "aw-watcher-window_test": {"type": "currentwindow"}
        }
        mock_events_resp = MagicMock()
        mock_events_resp.json.return_value = []
        mock_requests.get.side_effect = [mock_buckets_resp, mock_events_resp]

        from collectors import activitywatch_collector
        activitywatch_collector.collect("2026-10-02")

        params = mock_requests.get.call_args_list[1].kwargs["params"]
        assert params == {
            "start": "2026-10-02T00:00:00+09:00",
            "end": "2026-10-03T00:00:00+09:00",
        }

    @patch("collectors.activitywatch_collector.requests")
    def test_collect_counts_only_active_time_when_afk_bucket_exists(
        self, mock_requests
    ):
        """afk バケットがあれば、クエリ API で操作していた時間だけを数えること"""
        mock_buckets_resp = MagicMock()
        mock_buckets_resp.json.return_value = {
            "aw-watcher-window_test": {"type": "currentwindow"},
            "aw-watcher-afk_test": {"type": "afkstatus"},
        }
        mock_requests.get.return_value = mock_buckets_resp

        mock_query_resp = MagicMock()
        mock_query_resp.json.return_value = [
            [
                {"data": {"app": "Code.exe"}, "duration": 1200},
                {"data": {"app": "Code.exe"}, "duration": 600},
                {"data": {"app": "chrome.exe"}, "duration": 300},
            ]
        ]
        mock_requests.post.return_value = mock_query_resp

        from collectors import activitywatch_collector
        result = activitywatch_collector.collect("2026-10-02")

        payload = mock_requests.post.call_args.kwargs["json"]
        assert payload["timeperiods"] == [
            "2026-10-02T00:00:00+09:00/2026-10-03T00:00:00+09:00"
        ]
        query = "\n".join(payload["query"])
        assert 'query_bucket("aw-watcher-afk_test")' in query
        assert "filter_period_intersect" in query
        assert result["app_times"] == [
            {"app_name": "Code.exe", "duration_seconds": 1800},
            {"app_name": "chrome.exe", "duration_seconds": 300},
        ]

    @patch("collectors.activitywatch_collector.requests")
    def test_collect_returns_empty_summary_when_unreachable(self, mock_requests):
        """ActivityWatch に接続できなければ、合計も時間帯も空で返すこと"""
        import requests as real_requests

        mock_requests.ConnectionError = real_requests.ConnectionError
        mock_requests.RequestException = real_requests.RequestException
        mock_requests.get.side_effect = real_requests.ConnectionError()

        from collectors import activitywatch_collector
        result = activitywatch_collector.collect("2026-10-02")

        assert result == {"app_times": [], "timeline": []}


class TestBuildTimeline:
    """15分ごとの時間帯への振り分けのテスト"""

    DAY_START = datetime(2026, 10, 2, tzinfo=timezone(timedelta(hours=9)))
    DAY_END = DAY_START + timedelta(days=1)

    @staticmethod
    def _event(timestamp: str, seconds: float, app: str, title: str = "") -> dict:
        return {
            "timestamp": timestamp,
            "duration": seconds,
            "data": {"app": app, "title": title},
        }

    def _build(self, events):
        from collectors.activitywatch_collector import _build_timeline
        return _build_timeline(events, self.DAY_START, self.DAY_END)

    def test_sums_apps_within_slot_in_jst(self):
        """UTC の timestamp を JST の時間帯に入れ、同じ時間帯のアプリを合計して長い順に並べること"""
        timeline = self._build([
            self._event("2026-10-02T01:46:00+00:00", 120, "Code.exe"),
            self._event("2026-10-02T01:50:00+00:00", 300, "WindowsTerminal.exe"),
            self._event("2026-10-02T01:56:00+00:00", 180, "Code.exe"),
        ])

        assert timeline == [
            {
                "start": "10:45",
                "apps": [
                    {"app_name": "Code.exe", "duration_seconds": 300, "title": None},
                    {"app_name": "WindowsTerminal.exe", "duration_seconds": 300, "title": None},
                ],
            }
        ]

    def test_splits_event_across_slot_boundary(self):
        """時間帯の境目をまたぐイベントを境目で分け、使っていない時間帯は出さないこと"""
        timeline = self._build([
            self._event("2026-10-02T10:10:00+09:00", 600, "Code.exe"),
            self._event("2026-10-02T11:00:00+09:00", 60, "Code.exe"),
        ])

        assert [(s["start"], s["apps"][0]["duration_seconds"]) for s in timeline] == [
            ("10:00", 300),
            ("10:15", 300),
            ("11:00", 60),
        ]

    def test_clips_to_target_day(self):
        """対象日の外にはみ出した分は数えないこと"""
        timeline = self._build([
            self._event("2026-10-01T23:55:00+09:00", 600, "Code.exe"),
            self._event("2026-10-02T23:55:00+09:00", 600, "Code.exe"),
        ])

        assert [(s["start"], s["apps"][0]["duration_seconds"]) for s in timeline] == [
            ("00:00", 300),
            ("23:45", 300),
        ]

    def test_browser_keeps_longest_title_in_slot(self):
        """ブラウザだけ、その時間帯で合計が最も長かったページ名を持つこと"""
        timeline = self._build([
            self._event("2026-10-02T09:00:00+09:00", 120, "chrome.exe", "GitHub"),
            self._event("2026-10-02T09:02:00+09:00", 60, "chrome.exe", "YouTube"),
            self._event("2026-10-02T09:03:00+09:00", 120, "chrome.exe", "YouTube"),
            self._event("2026-10-02T09:05:00+09:00", 60, "Code.exe", "main.py"),
            self._event("2026-10-02T09:06:00+09:00", 60, "Google Chrome", "Docs"),
        ])

        apps = {a["app_name"]: a for a in timeline[0]["apps"]}
        assert apps["chrome.exe"]["title"] == "YouTube"
        assert apps["chrome.exe"]["duration_seconds"] == 300
        assert apps["Google Chrome"]["title"] == "Docs"
        assert apps["Code.exe"]["title"] is None

    def test_skips_events_without_timestamp(self):
        """timestamp の無いイベントは時間帯に入れないこと"""
        assert self._build([{"duration": 60, "data": {"app": "Code.exe"}}]) == []
