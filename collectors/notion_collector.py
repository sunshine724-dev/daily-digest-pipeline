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


def collect() -> list[NotionPageInfo]:
    """
    今日編集されたNotionページを取得する。

    Returns:
        NotionPageInfoのリスト
    """
    if not config.NOTION_API_TOKEN:
        logger.warning("NOTION_API_TOKEN が設定されていません。Notion収集をスキップします。")
        return []

    try:
        notion = Client(auth=config.NOTION_API_TOKEN)
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

                # 今日の日付でフィルタ
                if not last_edited.startswith(today_str):
                    # ソート済みなので、今日以外が出たら終了
                    has_more = False
                    break

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
