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


def collect_all(target_date_str: str) -> dict:
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
        "notion": ("notion_pages", lambda: notion_collector.collect(target_date_str)),
        "github": ("github_repos", lambda: github_collector.collect(target_date_str)),
        "chrome": ("chrome_sites", lambda: chrome_collector.collect(target_date_str)),
        "activitywatch": ("app_times", lambda: activitywatch_collector.collect(target_date_str)),
        "gcal": ("calendar_events", lambda: gcal_collector.collect(target_date_str)),
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
    today_str = now.strftime('%Y-%m-%d')
    logger.info(f"=== Daily Digest Pipeline 開始 ({now.strftime('%Y-%m-%d %H:%M:%S')} JST) ===")

    # 対象日のリストを作成
    target_dates = []
    if args.dry_run:
        # Dry-run時は今日のみ
        target_dates = [today_str]
    else:
        last_date_str = uploader.get_latest_processed_date()
        if last_date_str:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            today_date = now.date()
            
            # 翌日から今日までのリストを作成
            curr_date = last_date + timedelta(days=1)
            while curr_date <= today_date:
                target_dates.append(curr_date.strftime("%Y-%m-%d"))
                curr_date += timedelta(days=1)
            
            # すでに今日まで最新化されていれば何もせず終了する場合も考慮
            if not target_dates:
                 logger.info("最新のログがすでに作成されています。実行をスキップします。")
                 sys.exit(0)
        else:
            # Not found or first run
            target_dates = [today_str]
            logger.info(f"過去の履歴が見つからないため、今日({today_str})のみを実行します。")

    logger.info(f"対象となる日付: {target_dates}")

    all_success = True
    for target_date_str in target_dates:
        logger.info(f"--- 📅 {target_date_str} の処理を開始 ---")
        
        # 1. データ収集
        logger.info(f"📥 データ収集を開始 ({target_date_str})...")
        data = collect_all(target_date_str)

        # 2. フォーマット
        logger.info("📝 Markdownを生成中...")
        markdown = formatter.format_digest(
            notion_pages=data["notion_pages"],
            github_repos=data["github_repos"],
            chrome_sites=data["chrome_sites"],
            app_times=data["app_times"],
            calendar_events=data["calendar_events"],
            target_date_str=target_date_str
        )

        # 3. アップロード
        if args.dry_run:
            logger.info("🔍 DRY RUN モード — Notion更新はスキップします")
            success = uploader.upload(markdown, target_date=target_date_str, dry_run=True)
        else:
            logger.info(f"📤 MCPログデータベースを更新中... ({target_date_str})")
            success = uploader.upload(markdown, target_date=target_date_str, dry_run=False)

        if not success:
            logger.error(f"❌ {target_date_str} の記録に失敗しました。")
            all_success = False

    if all_success:
        logger.info("✅ Daily Digest Pipeline 完了")
    else:
        logger.error("❌ 一部またはすべての更新に失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()
