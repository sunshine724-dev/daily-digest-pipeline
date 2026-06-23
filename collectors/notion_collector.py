"""
Notion収集モジュール
Notion APIを使用して、今日編集されたページの一覧を取得する。
"""

import logging
from datetime import datetime, timezone
from typing import TypedDict

from notion_client import Client

import config

logger = logging.getLogger(__name__)


class NotionPageInfo(TypedDict):
    """Notionページ情報"""
    title: str
    url: str
    last_edited: str


def collect(target_date_str: str = "") -> list[NotionPageInfo]:
    """
    指定された日付に編集されたNotionページを取得する。
    
    Args:
        target_date_str: YYYY-MM-DD形式の日付文字列。未指定時は当日（UTC）を使う

    Returns:
        NotionPageInfoのリスト
    """
    if not config.NOTION_API_TOKEN:
        logger.warning("NOTION_API_TOKEN が設定されていません。Notion収集をスキップします。")
        return []

    if not target_date_str:
        target_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        notion = Client(auth=config.NOTION_API_TOKEN)

        results: list[NotionPageInfo] = []
        has_more = True
        start_cursor = None

        while has_more:
            # 今日編集されたページを検索
            response = notion.search(
                filter={"property": "object", "value": "page"},
                sort={"direction": "descending", "timestamp": "last_edited_time"},
                start_cursor=start_cursor,
            )

            for page in response.get("results", []):
                last_edited = page.get("last_edited_time", "")

                # 指定された日付でフィルタ
                if not last_edited.startswith(target_date_str):
                    # ソート済みであっても、指定日「以後」のものが混ざる可能性があるので、
                    # 前の日付が出た時点で打ち切るように処理する。
                    # ここでは一旦、違う日付が出たら対象外とする。
                    # ※ NotionのAPIレスポンスの順番に注意。ここでは降順（新しい順）。
                    # なので、指定日付より古いものが出たら終了する判定にするのが正確だが、
                    # 単純前方一致で指定日付のみ抽出するようにしておく。
                    if last_edited < target_date_str:
                        has_more = False
                        break
                    continue

                # タイトルを取得
                title = _extract_title(page)
                url = page.get("url", "")

                results.append(NotionPageInfo(
                    title=title,
                    url=url,
                    last_edited=last_edited,
                ))

            else:
                # breakされなかった場合、次のページがあるかチェック
                has_more = response.get("has_more", False)
                start_cursor = response.get("next_cursor")

            # 上限チェック
            if len(results) >= config.MAX_NOTION_PAGES:
                results = results[:config.MAX_NOTION_PAGES]
                break

        logger.info(f"Notion: {len(results)}件のページを取得しました。")
        return results

    except Exception as e:
        logger.error(f"Notion収集でエラーが発生しました: {e}")
        return []


def _extract_title(page: dict) -> str:
    """ページオブジェクトからタイトルを抽出する。"""
    properties = page.get("properties", {})

    # 各プロパティからtitleタイプのものを探す
    for prop in properties.values():
        if prop.get("type") == "title":
            title_items = prop.get("title", [])
            if title_items:
                return "".join(item.get("plain_text", "") for item in title_items)

    return "無題"
