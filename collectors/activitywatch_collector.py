"""
ActivityWatch収集モジュール
ActivityWatch REST APIから今日の時間配分データを取得する。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import TypedDict

import requests

import config

logger = logging.getLogger(__name__)


class AppTimeEntry(TypedDict):
    """アプリ別時間配分"""
    app_name: str
    duration_seconds: float


def collect() -> list[AppTimeEntry]:
    """
    ActivityWatchから今日のアプリ別時間配分を取得する。

    Returns:
        AppTimeEntryのリスト（使用時間の長い順）
    """
    base_url = config.AW_API_BASE.rstrip("/")

    try:
        # まず利用可能なバケットを取得
        buckets_url = f"{base_url}/api/0/buckets"
        resp = requests.get(buckets_url, timeout=5)
        resp.raise_for_status()
        buckets = resp.json()

        # aw-watcher-window バケットを探す
        window_bucket_id = None
        for bucket_id, bucket_info in buckets.items():
            if bucket_info.get("type") == "currentwindow":
                window_bucket_id = bucket_id
                break

        if not window_bucket_id:
            logger.warning("aw-watcher-window バケットが見つかりません。")
            return []

        # 今日の開始・終了時刻
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)

        # 今日のイベントを取得
        events_url = f"{base_url}/api/0/buckets/{window_bucket_id}/events"
        params = {
            "start": today_start.isoformat(),
            "end": tomorrow_start.isoformat(),
        }
        resp = requests.get(events_url, params=params, timeout=10)
        resp.raise_for_status()
        events = resp.json()

        # アプリ別に集計
        app_times: dict[str, float] = {}
        for event in events:
            data = event.get("data", {})
            app = data.get("app", "Unknown")
            duration = event.get("duration", 0)

            if app in app_times:
                app_times[app] += duration
            else:
                app_times[app] = duration

        # 使用時間の長い順にソート
        results = [
            AppTimeEntry(app_name=app, duration_seconds=dur)
            for app, dur in sorted(app_times.items(), key=lambda x: x[1], reverse=True)
        ]

        logger.info(f"ActivityWatch: {len(results)}件のアプリ使用データを取得しました。")
        return results

    except requests.ConnectionError:
        logger.warning("ActivityWatchに接続できません（起動していない可能性があります）。")
        return []
    except requests.RequestException as e:
        logger.error(f"ActivityWatch APIエラー: {e}")
        return []
    except Exception as e:
        logger.error(f"ActivityWatch収集でエラーが発生しました: {e}")
        return []
