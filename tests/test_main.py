"""
main モジュールのテスト
対象日の算出ロジックを検証する。
"""

from datetime import datetime, timezone

from main import build_target_dates


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