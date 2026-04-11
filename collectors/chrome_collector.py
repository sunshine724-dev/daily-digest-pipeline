"""
Chrome履歴収集モジュール
ChromeのSQLiteデータベースから今日のブラウザ履歴を取得する。
"""

import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TypedDict

import config

logger = logging.getLogger(__name__)

# Chrome の timestamps は 1601-01-01 からのマイクロ秒
# Unix epoch (1970-01-01) との差分
_CHROME_EPOCH_OFFSET = 11644473600 * 1_000_000


class ChromeSiteInfo(TypedDict):
    """Chrome訪問サイト情報"""
    title: str
    url: str
    visit_count: int


def collect(target_date_str: str) -> list[ChromeSiteInfo]:
    """
    指定日時のChromeブラウザ履歴を取得する。

    ChromeがDBをロックしている可能性があるため、
    一時ファイルにコピーしてから読み込む。

    Returns:
        ChromeSiteInfoのリスト（訪問回数の多い順）
    """
    history_path = config.CHROME_HISTORY_PATH

    if not history_path.exists():
        logger.warning(f"Chrome履歴ファイルが見つかりません: {history_path}")
        return []

    # 一時ファイルにコピー（Chromeのロック回避）
    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / "History"

    try:
        shutil.copy2(str(history_path), str(tmp_path))
    except (PermissionError, OSError) as e:
        logger.error(f"Chrome履歴ファイルのコピーに失敗しました: {e}")
        return []

    try:
        conn = sqlite3.connect(str(tmp_path))
        cursor = conn.cursor()

        # 対象日の開始時刻と終了時刻をChrome epochに変換
        # UTCとして扱い、その日の0時0分を設定
        dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        target_start_chrome = int(dt.timestamp() * 1_000_000) + _CHROME_EPOCH_OFFSET
        target_end_chrome = int((dt + timedelta(days=1)).timestamp() * 1_000_000) + _CHROME_EPOCH_OFFSET

        # 該当日に訪問したURLを訪問回数付きで取得
        query = """
            SELECT u.url, u.title, COUNT(v.id) as visit_count
            FROM urls u
            JOIN visits v ON u.id = v.url
            WHERE v.visit_time >= ? AND v.visit_time < ?
            GROUP BY u.url
            ORDER BY visit_count DESC
            LIMIT ?
        """
        cursor.execute(query, (target_start_chrome, target_end_chrome, config.MAX_CHROME_SITES))

        results: list[ChromeSiteInfo] = []
        for url, title, visit_count in cursor.fetchall():
            # 内部URL（chrome://等）を除外
            if url.startswith("chrome://") or url.startswith("chrome-extension://"):
                continue

            results.append(ChromeSiteInfo(
                title=title or url,
                url=url,
                visit_count=visit_count,
            ))

        conn.close()
        logger.info(f"Chrome: {len(results)}件のサイトを取得しました。")
        return results

    except sqlite3.Error as e:
        logger.error(f"Chrome履歴DBの読み込みに失敗しました: {e}")
        return []
    finally:
        # 一時ファイルを削除
        try:
            shutil.rmtree(tmp_dir)
        except OSError:
            pass
