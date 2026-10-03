"""
設定管理モジュール
.envファイルから環境変数を読み込み、アプリ全体で使用する設定値を提供する。
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .envファイルの読み込み
load_dotenv(Path(__file__).parent / ".env")


# === 端末 ===
ALL_COLLECTORS: tuple[str, ...] = (
    "notion",
    "github",
    "chrome",
    "activitywatch",
    "gcal",
    "whatpulse",
)

# Mac では PC ごとのデータだけを集める。Chrome は Win の履歴に他端末の閲覧が同期されており、
# Notion・GitHub・カレンダーはアカウント全体のデータなので、Win 側だけで集める（2026-10-03 決定）
MAC_COLLECTORS: tuple[str, ...] = ("activitywatch", "whatpulse")


def default_device_name(platform: str) -> str:
    """OS から Daily Digest DB の「端末」列に入れる値を決める。"""
    return "Mac" if platform == "darwin" else "Win"


def default_collectors(device_name: str) -> tuple[str, ...]:
    """端末ごとの既定の収集対象を返す。"""
    return MAC_COLLECTORS if device_name == "Mac" else ALL_COLLECTORS


def parse_collectors(value: str) -> tuple[str, ...]:
    """カンマ区切りの収集対象名を tuple にする。空要素は捨てる。"""
    return tuple(name.strip() for name in value.split(",") if name.strip())


# .env の指定が無いときは OS から決める。Mac で書き忘れても Win のページを上書きしないようにするため
DEVICE_NAME: str = os.getenv("DEVICE_NAME") or default_device_name(sys.platform)
COLLECTORS: tuple[str, ...] = (
    parse_collectors(os.getenv("COLLECTORS", "")) or default_collectors(DEVICE_NAME)
)


# === Notion API ===
NOTION_API_TOKEN: str = os.getenv("NOTION_API_TOKEN", "")
MCP_LOG_PAGE_ID: str = os.getenv("MCP_LOG_PAGE_ID", "8a6ce048c8e54b5db4c149a5ff5bb178")
MCP_LOG_DB_ID: str = os.getenv("MCP_LOG_DB_ID", "")

# === GitHub API ===
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME: str = os.getenv("GITHUB_USERNAME", "")

# === ActivityWatch ===
AW_API_BASE: str = os.getenv("AW_API_BASE", "http://localhost:5600")

# === Chrome ===
CHROME_PROFILE: str = os.getenv("CHROME_PROFILE", "Default")

# Chromeの履歴DBパス（Windows）
CHROME_HISTORY_PATH: Path = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / "Google" / "Chrome" / "User Data" / CHROME_PROFILE / "History"
)

# === WhatPulse ===
WHATPULSE_API_BASE: str = os.getenv("WHATPULSE_API_BASE", "http://localhost:3490")

# === 出力設定 ===
MAX_HIGHLIGHTS: int = 5
MAX_CHROME_SITES: int = 10
MAX_NOTION_PAGES: int = 15
MAX_GITHUB_REPOS: int = 10

# === 日付調整 ===
# 実行日から何日ずらした日付を対象にするか。
# 例: -1 なら昨日、0 なら当日、1 なら翌日を対象にする。
TARGET_DATE_OFFSET_DAYS: int = int(os.getenv("TARGET_DATE_OFFSET_DAYS", "-1"))
