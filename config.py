"""
設定管理モジュール
.envファイルから環境変数を読み込み、アプリ全体で使用する設定値を提供する。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# .envファイルの読み込み
load_dotenv(Path(__file__).parent / ".env")


# === Notion API ===
NOTION_API_TOKEN: str = os.getenv("NOTION_API_TOKEN", "")
MCP_LOG_PAGE_ID: str = os.getenv("MCP_LOG_PAGE_ID", "8a6ce048c8e54b5db4c149a5ff5bb178")

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

# === 出力設定 ===
MAX_HIGHLIGHTS: int = 5
MAX_CHROME_SITES: int = 10
MAX_NOTION_PAGES: int = 15
MAX_GITHUB_REPOS: int = 10
