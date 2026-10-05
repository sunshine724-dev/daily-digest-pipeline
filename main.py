"""
Daily Digest Pipeline — メインオーケストレータ
各収集モジュールを並列実行し、結果をフォーマットしてMCPログページを更新する。

使用方法:
    python main.py              # 通常実行
    python main.py --dry-run    # Notion更新なし（ターミナル出力のみ）
    python main.py --require-active-user --skip-if-done  # 定期起動用（Mac の launchd）
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path

from collectors import (
    notion_collector,
    github_collector,
    chrome_collector,
    activitywatch_collector,
    gcal_collector,
    whatpulse_collector,
)
import formatter
import uploader
import config
import user_activity


# 日本時間オフセット
_JST = timezone(timedelta(hours=9))

# Mac が DarkWake で数秒だけ起きた時点で起動すると、通信中に再スリープして
# 何時間も止まるため、直近に操作がない回は実行しない
_ACTIVE_USER_IDLE_LIMIT_SECONDS = 10 * 60


# ロギング設定
def setup_logging() -> None:
    """ロギングの初期設定を行う。"""
    log_dir = Path(".log")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"daily-digest-{datetime.now(_JST).strftime('%Y%m%d')}.log"

    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
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
        "whatpulse_stats": None,
    }

    # 収集タスクの定義
    tasks = {
        "notion": ("notion_pages", lambda: notion_collector.collect(target_date_str)),
        "github": ("github_repos", lambda: github_collector.collect(target_date_str)),
        "chrome": ("chrome_sites", lambda: chrome_collector.collect(target_date_str)),
        "activitywatch": (
            "app_times",
            lambda: activitywatch_collector.collect(target_date_str),
        ),
        "gcal": ("calendar_events", lambda: gcal_collector.collect(target_date_str)),
        "whatpulse": (
            "whatpulse_stats",
            lambda: whatpulse_collector.collect(target_date_str),
        ),
    }

    unknown = [name for name in config.COLLECTORS if name not in tasks]
    if unknown:
        logger.warning(f"不明な収集対象を無視します: {unknown}")
    enabled = {
        name: task for name, task in tasks.items() if name in config.COLLECTORS
    }
    logger.info(f"端末: {config.DEVICE_NAME} / 収集対象: {list(enabled)}")

    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_name = {}
        for name, (key, func) in enabled.items():
            future = executor.submit(func)
            future_to_name[future] = (name, key)

        for future in as_completed(future_to_name):
            name, key = future_to_name[future]
            try:
                result = future.result()
                results[key] = result
                # WhatPulseはリストではなく辞書またはNoneを返す
                if isinstance(result, dict):
                    logger.info(f"✅ {name} 収集完了")
                elif result is None:
                    logger.info(f"⚠️ {name} データなし")
                else:
                    logger.info(f"✅ {name} 収集完了: {len(result)}件")
            except Exception as e:
                logger.error(f"❌ {name} 収集失敗: {e}")

    return results


def build_target_dates(
    now: datetime,
    last_date_str: str | None,
    dry_run: bool,
    date_offset_days: int,
) -> list[str]:
    """実行基準日時から収集対象の日付一覧を作る。"""
    shifted_now = now + timedelta(days=date_offset_days)
    shifted_today_str = shifted_now.strftime("%Y-%m-%d")

    if dry_run:
        return [shifted_today_str]

    target_dates: list[str] = []
    if last_date_str:
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        shifted_today_date = shifted_now.date()

        curr_date = last_date + timedelta(days=1)
        while curr_date <= shifted_today_date:
            target_dates.append(curr_date.strftime("%Y-%m-%d"))
            curr_date += timedelta(days=1)

        if not target_dates:
            target_dates = [shifted_today_str]
    else:
        target_dates = [shifted_today_str]

    return target_dates


def find_skip_reason(
    target_date_str: str,
    require_active_user: bool,
    skip_if_done: bool,
) -> str | None:
    """
    定期起動の回を実行せずに終えるべきかを判定する。

    Args:
        target_date_str: この回の対象日（例: '2026-10-04'）
        require_active_user: 直近に操作がなければ実行しない
        skip_if_done: この端末の対象日のページがあれば実行しない

    Returns:
        実行しない理由。実行すべきならNone

    Raises:
        requests.RequestException: skip_if_done の確認でNotion APIに失敗した場合
    """
    if require_active_user:
        idle_seconds = user_activity.get_idle_seconds()
        if idle_seconds is not None and idle_seconds >= _ACTIVE_USER_IDLE_LIMIT_SECONDS:
            return f"最後の操作から {idle_seconds / 60:.0f} 分経過しているため実行しません。"

    if skip_if_done and uploader.page_exists(target_date_str):
        return f"{target_date_str} のページは作成済みのため実行しません。"

    return None


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
    parser.add_argument(
        "--date-offset",
        type=int,
        default=None,
        help="実行日から収集対象日を何日ずらすか（例: -1で昨日、1で翌日）",
    )
    parser.add_argument(
        "--require-active-user",
        action="store_true",
        help="最後のキーボード・マウス操作から10分以上経っていれば何もせず終了する",
    )
    parser.add_argument(
        "--skip-if-done",
        action="store_true",
        help="この端末の対象日のページが作成済みなら何もせず終了する",
    )
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    now = datetime.now(_JST)
    date_offset_days = (
        args.date_offset if args.date_offset is not None else config.TARGET_DATE_OFFSET_DAYS
    )
    shifted_now = now + timedelta(days=date_offset_days)
    shifted_today_str = shifted_now.strftime("%Y-%m-%d")
    logger.info(
        f"=== Daily Digest Pipeline 開始 ({now.strftime('%Y-%m-%d %H:%M:%S')} JST) ==="
    )
    logger.info(f"対象日オフセット: {date_offset_days}日")

    if not args.dry_run:
        skip_reason = find_skip_reason(
            target_date_str=shifted_today_str,
            require_active_user=args.require_active_user,
            skip_if_done=args.skip_if_done,
        )
        if skip_reason:
            logger.info(skip_reason)
            return

    # 対象日のリストを作成
    last_date_str = None if args.dry_run else uploader.get_latest_processed_date()
    target_dates = build_target_dates(
        now=now,
        last_date_str=last_date_str,
        dry_run=args.dry_run,
        date_offset_days=date_offset_days,
    )

    if args.dry_run:
        logger.info(f"Dry-run時は対象日を {shifted_today_str} に設定します。")
    elif not last_date_str:
        logger.info(
            f"過去の履歴が見つからないため、対象日は {shifted_today_str} のみを実行します。"
        )
    elif target_dates == [shifted_today_str]:
        logger.info(
            f"最新日付は対象日({shifted_today_str})のため、対象日分を再生成して更新します。"
        )

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
            whatpulse_stats=data["whatpulse_stats"],
            target_date_str=target_date_str,
        )

        # 3. アップロード
        if args.dry_run:
            logger.info("🔍 DRY RUN モード — Notion更新はスキップします")
            success = uploader.upload(
                markdown, target_date=target_date_str, dry_run=True
            )
        else:
            logger.info(f"📤 MCPログデータベースを更新中... ({target_date_str})")
            success = uploader.upload(
                markdown, target_date=target_date_str, dry_run=False
            )

        if not success:
            logger.error(f"❌ {target_date_str} の記録に失敗しました。")
            all_success = False

    if all_success:
        logger.info("✅ Daily Digest Pipeline 完了")
    else:
        logger.error("❌ 一部またはすべての更新に失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # setup_logging前の致命的エラーでもファイルに残せるようにする
        if not logging.getLogger().handlers:
            setup_logging()
        logging.getLogger(__name__).exception("予期しない例外により処理を終了しました")
        sys.exit(1)
