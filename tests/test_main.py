"""
main モジュールのテスト
対象日の算出ロジックを検証する。
"""

from datetime import datetime, timezone
from unittest.mock import patch

import config
from main import build_target_dates, collect_all


class TestCollectAll:
    """収集対象の絞り込みのテスト"""

    @patch("main.whatpulse_collector")
    @patch("main.gcal_collector")
    @patch("main.activitywatch_collector")
    @patch("main.chrome_collector")
    @patch("main.github_collector")
    @patch("main.notion_collector")
    def test_runs_only_configured_collectors(
        self, notion, github, chrome, activitywatch, gcal, whatpulse, monkeypatch
    ):
        monkeypatch.setattr(config, "COLLECTORS", ("activitywatch", "whatpulse"))
        activitywatch.collect.return_value = {
            "app_times": [{"app_name": "Code", "duration_seconds": 60}],
            "timeline": [{"start": "09:00", "apps": []}],
        }
        whatpulse.collect.return_value = {"keys": 1}

        result = collect_all("2026-10-03")

        activitywatch.collect.assert_called_once_with("2026-10-03")
        whatpulse.collect.assert_called_once_with("2026-10-03")
        for skipped in (notion, github, chrome, gcal):
            skipped.collect.assert_not_called()
        assert result["chrome_sites"] == []
        assert result["app_times"] == [{"app_name": "Code", "duration_seconds": 60}]
        assert result["timeline"] == [{"start": "09:00", "apps": []}]

    @patch("main.activitywatch_collector")
    def test_activity_defaults_to_empty_when_not_collected(
        self, activitywatch, monkeypatch
    ):
        monkeypatch.setattr(config, "COLLECTORS", ())

        result = collect_all("2026-10-03")

        assert result["app_times"] == []
        assert result["timeline"] == []
        assert "activity" not in result


class TestBuildTargetDates:
    """対象日算出のテスト"""

    def test_dry_run_uses_shifted_today(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        result = build_target_dates(
            now=now,
            last_date_str=None,
            dry_run=True,
            date_offset_days=-1,
        )

        assert result == ["2026-06-22"]

    def test_backfill_uses_shifted_today_as_upper_bound(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        result = build_target_dates(
            now=now,
            last_date_str="2026-06-20",
            dry_run=False,
            date_offset_days=-1,
        )

        assert result == ["2026-06-21", "2026-06-22"]

    def test_single_day_when_no_gap(self):
        now = datetime(2026, 6, 23, 12, 0, tzinfo=timezone.utc)

        result = build_target_dates(
            now=now,
            last_date_str="2026-06-22",
            dry_run=False,
            date_offset_days=-1,
        )

        assert result == ["2026-06-22"]