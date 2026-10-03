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

# 対象日は JST の 0:00〜24:00 で区切る（以前は UTC で切っており、JST 9:00〜翌9:00 を数えていた）
_JST = timezone(timedelta(hours=9))


class AppTimeEntry(TypedDict):
    """アプリ別時間配分"""
    app_name: str
    duration_seconds: float


def _find_bucket(buckets: dict, bucket_type: str) -> str | None:
    """指定した type の最初のバケットIDを返す。無ければNone。"""
    for bucket_id, bucket_info in buckets.items():
        if bucket_info.get("type") == bucket_type:
            return bucket_id
    return None


def _query_active_window_events(
    base_url: str,
    window_bucket_id: str,
    afk_bucket_id: str,
    start: datetime,
    end: datetime,
) -> list[dict]:
    """
    クエリ API で、操作していた（not-afk）区間と重なるウィンドウイベントだけを返す。
    ActivityWatch の画面が「アクティブな時間」を出すときと同じ計算。
    """
    query = [
        f'window_events = query_bucket("{window_bucket_id}");',
        f'afk_events = query_bucket("{afk_bucket_id}");',
        'not_afk = filter_keyvals(afk_events, "status", ["not-afk"]);',
        "RETURN = filter_period_intersect(window_events, not_afk);",
    ]
    payload = {
        "timeperiods": [f"{start.isoformat()}/{end.isoformat()}"],
        "query": query,
    }
    resp = requests.post(f"{base_url}/api/0/query/", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()[0]


def _fetch_window_events(
    base_url: str, window_bucket_id: str, start: datetime, end: datetime
) -> list[dict]:
    """ウィンドウイベントを離席判定なしでそのまま返す。"""
    events_url = f"{base_url}/api/0/buckets/{window_bucket_id}/events"
    params = {"start": start.isoformat(), "end": end.isoformat()}
    resp = requests.get(events_url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _sum_by_app(events: list[dict]) -> list[AppTimeEntry]:
    """イベントをアプリ別に合計し、使用時間の長い順に並べる。"""
    app_times: dict[str, float] = {}
    for event in events:
        app = event.get("data", {}).get("app", "Unknown")
        app_times[app] = app_times.get(app, 0) + event.get("duration", 0)

    return [
        AppTimeEntry(app_name=app, duration_seconds=dur)
        for app, dur in sorted(app_times.items(), key=lambda x: x[1], reverse=True)
    ]


def collect(target_date_str: str = "") -> list[AppTimeEntry]:
    """
    ActivityWatchから指定日のアプリ別時間配分を取得する。
    afk バケットがあれば、操作していた時間だけを数える。

    Args:
        target_date_str: YYYY-MM-DD形式の日付文字列

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

        window_bucket_id = _find_bucket(buckets, "currentwindow")
        if not window_bucket_id:
            logger.warning("aw-watcher-window バケットが見つかりません。")
            return []
        afk_bucket_id = _find_bucket(buckets, "afkstatus")

        # 対象日の開始・終了時刻
        if not target_date_str:
            target_date_str = datetime.now(_JST).strftime("%Y-%m-%d")

        # target_date_str は "YYYY-MM-DD" なのでパースする
        dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=_JST)
        target_start = dt
        tomorrow_start = target_start + timedelta(days=1)

        if afk_bucket_id:
            events = _query_active_window_events(
                base_url, window_bucket_id, afk_bucket_id, target_start, tomorrow_start
            )
        else:
            # 離席中も前面のアプリの時間として数えられるので、合計は実際の操作時間より長くなる
            logger.warning(
                "aw-watcher-afk バケットが見つからないため、離席中の時間も含めて集計します。"
            )
            events = _fetch_window_events(
                base_url, window_bucket_id, target_start, tomorrow_start
            )

        results = _sum_by_app(events)
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
