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

SLOT_MINUTES = 15
_SLOT = timedelta(minutes=SLOT_MINUTES)


class AppTimeEntry(TypedDict):
    """アプリ別時間配分"""
    app_name: str
    duration_seconds: float


class SlotAppEntry(TypedDict):
    """時間帯の中のアプリ別時間。title はブラウザのときだけ、その時間帯で最も長く見たページ名が入る。"""
    app_name: str
    duration_seconds: float
    title: str | None


class TimelineSlot(TypedDict):
    """15分の時間帯1つ分。start は JST の "HH:MM"、apps は使用時間の長い順。"""
    start: str
    apps: list[SlotAppEntry]


class ActivitySummary(TypedDict):
    """ActivityWatch の収集結果。app_times は1日の合計、timeline は使った時間帯だけを時刻順に持つ。"""
    app_times: list[AppTimeEntry]
    timeline: list[TimelineSlot]


def _is_browser(app_name: str) -> bool:
    return "chrome" in app_name.lower()


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


def _build_timeline(
    events: list[dict], day_start: datetime, day_end: datetime
) -> list[TimelineSlot]:
    """
    イベントを15分の時間帯に振り分け、時間帯ごとにアプリ別の時間を合計する。
    時間帯の境目をまたぐイベントは境目で分けて両方に配る。対象日の外にはみ出した分と、
    timestamp の無いイベントは数えない。
    """
    slot_apps: dict[datetime, dict[str, float]] = {}
    slot_titles: dict[datetime, dict[str, dict[str, float]]] = {}

    for event in events:
        timestamp = event.get("timestamp")
        if not timestamp:
            continue
        raw_start = datetime.fromisoformat(timestamp).astimezone(_JST)
        start = max(raw_start, day_start)
        end = min(raw_start + timedelta(seconds=event.get("duration", 0)), day_end)
        data = event.get("data", {})
        app = data.get("app", "Unknown")
        title = data.get("title", "")

        while start < end:
            slot_start = day_start + _SLOT * ((start - day_start) // _SLOT)
            piece_end = min(slot_start + _SLOT, end)
            seconds = (piece_end - start).total_seconds()
            apps = slot_apps.setdefault(slot_start, {})
            apps[app] = apps.get(app, 0) + seconds
            if _is_browser(app) and title:
                titles = slot_titles.setdefault(slot_start, {}).setdefault(app, {})
                titles[title] = titles.get(title, 0) + seconds
            start = piece_end

    timeline: list[TimelineSlot] = []
    for slot_start in sorted(slot_apps):
        entries = []
        for app, seconds in sorted(
            slot_apps[slot_start].items(), key=lambda x: x[1], reverse=True
        ):
            titles = slot_titles.get(slot_start, {}).get(app)
            longest_title = max(titles, key=titles.get) if titles else None
            entries.append(
                SlotAppEntry(app_name=app, duration_seconds=seconds, title=longest_title)
            )
        timeline.append(TimelineSlot(start=slot_start.strftime("%H:%M"), apps=entries))
    return timeline


def _empty_summary() -> ActivitySummary:
    return ActivitySummary(app_times=[], timeline=[])


def collect(target_date_str: str = "") -> ActivitySummary:
    """
    ActivityWatchから指定日のアプリ別時間配分と、15分ごとの時間帯別の使用アプリを取得する。
    afk バケットがあれば、操作していた時間だけを数える。

    Args:
        target_date_str: YYYY-MM-DD形式の日付文字列（JST）

    Returns:
        ActivitySummary。取得できなければ app_times・timeline とも空
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
            return _empty_summary()
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

        app_times = _sum_by_app(events)
        timeline = _build_timeline(events, target_start, tomorrow_start)
        logger.info(
            f"ActivityWatch: {len(app_times)}件のアプリ使用データと"
            f"{len(timeline)}個の時間帯を取得しました。"
        )
        return ActivitySummary(app_times=app_times, timeline=timeline)

    except requests.ConnectionError:
        logger.warning("ActivityWatchに接続できません（起動していない可能性があります）。")
        return _empty_summary()
    except requests.RequestException as e:
        logger.error(f"ActivityWatch APIエラー: {e}")
        return _empty_summary()
    except Exception as e:
        logger.error(f"ActivityWatch収集でエラーが発生しました: {e}")
        return _empty_summary()
