"""
フォーマッタモジュール
各収集モジュールの結果を受け取り、MCPログ形式のMarkdownを生成する。
"""

import logging
from datetime import datetime, timezone, timedelta

import config
from collectors.notion_collector import NotionPageInfo
from collectors.github_collector import GitHubRepoActivity
from collectors.chrome_collector import ChromeSiteInfo
from collectors.activitywatch_collector import AppTimeEntry, TimelineSlot
from collectors.gcal_collector import CalendarEventInfo
from collectors.whatpulse_collector import WhatPulseStats

logger = logging.getLogger(__name__)

# 日本時間（JST）のオフセット
_JST = timezone(timedelta(hours=9))

# uploader はこの接頭辞の見出しを折りたたみ見出しにし、直後の箇条書きを中に入れる
TOGGLE_HEADING_PREFIX = "### ▶ "

TIMELINE_MAX_APPS = 3
TIMELINE_TITLE_MAX_CHARS = 40
_BROWSER_TITLE_SUFFIXES = (" - Google Chrome",)


def _timeline_app_name(app_name: str) -> str:
    return app_name.removesuffix(".exe")


def _timeline_title(title: str) -> str:
    for suffix in _BROWSER_TITLE_SUFFIXES:
        title = title.removesuffix(suffix)
    if len(title) > TIMELINE_TITLE_MAX_CHARS:
        return title[:TIMELINE_TITLE_MAX_CHARS] + "…"
    return title


def format_timeline_line(slot: TimelineSlot) -> str | None:
    """
    15分の時間帯1つを `10:45 Code 9m, chrome 4m（ページ名）, 他 2m` の1行にする。
    1分未満のアプリは載せず、上位 TIMELINE_MAX_APPS 個より後は「他」にまとめる。
    載せるアプリが無ければ None。
    """
    minutes = [(app, round(app["duration_seconds"] / 60)) for app in slot["apps"]]
    shown = [(app, m) for app, m in minutes if m >= 1][:TIMELINE_MAX_APPS]
    if not shown:
        return None

    parts = []
    for app, m in shown:
        part = f"{_timeline_app_name(app['app_name'])} {m}m"
        if app["title"]:
            part += f"（{_timeline_title(app['title'])}）"
        parts.append(part)

    shown_ids = {id(app) for app, _ in shown}
    rest_seconds = sum(
        app["duration_seconds"] for app in slot["apps"] if id(app) not in shown_ids
    )
    rest_minutes = round(rest_seconds / 60)
    if rest_minutes >= 1:
        parts.append(f"他 {rest_minutes}m")

    return f"{slot['start']} " + ", ".join(parts)


def format_duration(seconds: float) -> str:
    """秒数を 'Xh Ym' 形式に変換する。"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def generate_highlights(
    notion_pages: list[NotionPageInfo],
    github_repos: list[GitHubRepoActivity],
    chrome_sites: list[ChromeSiteInfo],
    app_times: list[AppTimeEntry],
    calendar_events: list[CalendarEventInfo] | None = None,
    whatpulse_stats: WhatPulseStats | None = None,
) -> list[str]:
    """
    各データソースからハイライト項目（最大5つ）を自動生成する。
    """
    highlights: list[str] = []

    # GitHubアクティビティからハイライト生成
    for repo in github_repos[:2]:
        total = repo["commits"]
        name = repo["repo_name"].split("/")[-1]  # owner/repo → repo
        top_msg = repo["commit_messages"][0] if repo["commit_messages"] else ""
        if top_msg:
            highlights.append(f"{name}: {top_msg}（計{total}コミット）")
        else:
            highlights.append(f"{name}: {total}コミット")

    # カレンダーイベントからハイライト生成
    if calendar_events:
        count = len(calendar_events)
        highlights.append(f"今日の予定: {count}件")

    # Notionアクティビティからハイライト生成
    if notion_pages:
        count = len(notion_pages)
        highlights.append(f"Notionで{count}ページを編集")

    # 主要アプリ使用時間からハイライト生成
    if app_times:
        top_app = app_times[0]
        dur = format_duration(top_app["duration_seconds"])
        highlights.append(f"{top_app['app_name']} を最も使用（{dur}）")

    # Chromeからハイライト生成
    if chrome_sites:
        top_site = chrome_sites[0]
        highlights.append(f"{top_site['title']} を最も閲覧（{top_site['visit_count']}回）")

    # WhatPulseからハイライト生成
    if whatpulse_stats:
        keys = whatpulse_stats['keys']
        clicks = whatpulse_stats['clicks']
        highlights.append(f"キー入力: {keys:,}回 / クリック: {clicks:,}回")

    return highlights[:config.MAX_HIGHLIGHTS]


def format_digest(
    notion_pages: list[NotionPageInfo],
    github_repos: list[GitHubRepoActivity],
    chrome_sites: list[ChromeSiteInfo],
    app_times: list[AppTimeEntry],
    calendar_events: list[CalendarEventInfo] | None = None,
    whatpulse_stats: WhatPulseStats | None = None,
    target_date_str: str = "",
    timeline: list[TimelineSlot] | None = None,
) -> str:
    """
    収集データからMCPログ形式のMarkdownを生成する。

    Args:
        notion_pages: Notion収集結果
        github_repos: GitHub収集結果
        chrome_sites: Chrome収集結果
        app_times: ActivityWatch収集結果（1日のアプリ別合計）
        timeline: ActivityWatch収集結果（15分ごとの時間帯）。末尾に折りたたみで載せる

    Returns:
        MCPログ用のMarkdown文字列
    """
    now = datetime.now(_JST)
    display_date = target_date_str if target_date_str else now.strftime("%Y-%m-%d")

    lines: list[str] = []

    # === ヘッダー ===
    lines.append(f"## 📋 Daily Digest — {display_date}")
    lines.append("")

    # === ハイライト ===
    highlights = generate_highlights(notion_pages, github_repos, chrome_sites, app_times, calendar_events, whatpulse_stats)
    if highlights:
        lines.append("### 🔖 Highlights")
        for i, h in enumerate(highlights, 1):
            lines.append(f"{i}. {h}")
        lines.append("")

    # === カレンダー ===
    if calendar_events:
        lines.append("### 📅 Calendar")
        for event in calendar_events:
            if event["is_all_day"]:
                lines.append(f"- 🔹 {event['summary']}（終日）")
            else:
                lines.append(f"- 🔹 {event['start_time']}–{event['end_time']}  {event['summary']}")
        lines.append("")

    # === リンク ===
    lines.append("### 🔗 Links")

    # A: Notionページ
    lines.append("**A: Notion**")
    if notion_pages:
        for page in notion_pages[:10]:
            lines.append(f"- [{page['title']}]({page['url']})")
    else:
        lines.append("- （今日のアクティビティなし）")
    lines.append("")

    # B: GitHub
    lines.append("**B: GitHub**")
    if github_repos:
        for repo in github_repos:
            name = repo["repo_name"].split("/")[-1]
            commits = repo["commits"]
            lines.append(f"- [{name}]({repo['repo_url']}): {commits} commits")
    else:
        lines.append("- （今日のアクティビティなし）")
    lines.append("")

    # === 時間配分 ===
    if app_times:
        lines.append("### ⏱ Time Tracking")
        lines.append("| アプリ | 時間 |")
        lines.append("|--------|------|")
        for entry in app_times[:10]:
            dur = format_duration(entry["duration_seconds"])
            lines.append(f"| {entry['app_name']} | {dur} |")
        lines.append("")

    # === Chrome上位サイト ===
    if chrome_sites:
        lines.append("### 📝 Chrome Top Sites")
        for i, site in enumerate(chrome_sites[:config.MAX_CHROME_SITES], 1):
            lines.append(f"{i}. {site['title']} ({site['visit_count']} visits)")
        lines.append("")

    # === WhatPulse入力・ネットワーク ===
    if whatpulse_stats:
        lines.append("### ⌨️ Input & Network (WhatPulse)")
        lines.append("| 項目 | 値 |")
        lines.append("|------|-----|")
        lines.append(f"| キー入力 | {whatpulse_stats['keys']:,} 回 |")
        lines.append(f"| クリック | {whatpulse_stats['clicks']:,} 回 |")
        lines.append(f"| スクロール | {whatpulse_stats['scrolls']:,} 回 |")
        lines.append(f"| ダウンロード | {whatpulse_stats['download_mb']:.1f} MB |")
        lines.append(f"| アップロード | {whatpulse_stats['upload_mb']:.1f} MB |")
        uptime_h = whatpulse_stats['uptime_seconds'] // 3600
        uptime_m = (whatpulse_stats['uptime_seconds'] % 3600) // 60
        lines.append(f"| 稼働時間 | {uptime_h}h {uptime_m:02d}m |")
        lines.append("")

    # === 15分ごとの時間帯（日次ログの突き合わせ用。人が見るときは閉じておく） ===
    timeline_lines = [
        line for line in (format_timeline_line(slot) for slot in timeline or []) if line
    ]
    if timeline_lines:
        lines.append(f"{TOGGLE_HEADING_PREFIX}🕒 Timeline（15分・JST）")
        for line in timeline_lines:
            lines.append(f"- {line}")
        lines.append("")

    # === フッター ===
    lines.append("---")
    lines.append(f"*自動生成: {now.strftime('%Y-%m-%d %H:%M:%S')} JST*")

    return "\n".join(lines)
