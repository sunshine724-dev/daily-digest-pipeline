"""
Daily Digest Pipeline — メインオーケストレータ
各収集モジュールを並列実行し、結果をフォーマットしてMCPログページを更新する。

使用方法:
    python main.py              # 通常実行
    python main.py --dry-run    # Notion更新なし（ターミナル出力のみ）
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from collectors import notion_collector, github_collector, chrome_collector, activitywatch_collector, gcal_collector
from collectors.notion_collector import NotionPageInfo
from collectors.github_collector import GitHubRepoActivity
from collectors.chrome_collector import ChromeSiteInfo
from collectors.activitywatch_collector import AppTimeEntry
import formatter
import uploader

# 日本時間オフセット
_JST = timezone(timedelta(hours=9))

# ロギング設定
def setup_logging() -> None:
    """ロギングの初期設定を行う。"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def collect_all() -> dict:
    """
    全収集モジュールを並列実行して結果を返す。
    各モジュールのエラーは個別にハンドリングされ、
    失敗しても他のモジュールの結果は返される（graceful degradation）。

    Returns:
        各データソースの収集結果を含む辞書
    """
    logger = logging.getLogger(__name__)
    results = {
        "notion_pages": [],
        "github_repos": [],
        "chrome_sites": [],
        "app_times": [],
        "calendar_events": [],
    }

    # 収集タスクの定義
    tasks = {
        "notion": ("notion_pages", notion_collector.collect),
        "github": ("github_repos", github_collector.collect),
        "chrome": ("chrome_sites", chrome_collector.collect),
        "activitywatch": ("app_times", activitywatch_collector.collect),
        "gcal": ("calendar_events", gcal_collector.collect),
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_name = {}
        for name, (key, func) in tasks.items():
            future = executor.submit(func)
            future_to_name[future] = (name, key)

        for future in as_completed(future_to_name):
            name, key = future_to_name[future]
            try:
                result = future.result()
                results[key] = result
                logger.info(f"✅ {name} 収集完了: {len(result)}件")
            except Exception as e:
                logger.error(f"❌ {name} 収集失敗: {e}")

    return results


def main() -> None:
    """メイン処理"""
    parser = argparse.ArgumentParser(
        description="Daily Digest Pipeline — 毎日の作業ログを自動収集しMCPログを更新"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Notion更新を行わず、生成されたMarkdownをターミナルに出力する",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    now = datetime.now(_JST)
    logger.info(f"=== Daily Digest Pipeline 開始 ({now.strftime('%Y-%m-%d %H:%M:%S')} JST) ===")

    # 1. データ収集
    logger.info("📥 データ収集を開始...")
    data = collect_all()

    # 2. フォーマット
    logger.info("📝 Markdownを生成中...")
    markdown = formatter.format_digest(
        notion_pages=data["notion_pages"],
        github_repos=data["github_repos"],
        chrome_sites=data["chrome_sites"],
        app_times=data["app_times"],
        calendar_events=data["calendar_events"],
    )

    # 3. アップロード
    if args.dry_run:
        logger.info("🔍 DRY RUN モード — Notion更新はスキップします")
    else:
        logger.info("📤 MCPログページを更新中...")

    success = uploader.upload(markdown, dry_run=args.dry_run)

    if success:
        logger.info("✅ Daily Digest Pipeline 完了")
    else:
        logger.error("❌ MCPログページの更新に失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()
