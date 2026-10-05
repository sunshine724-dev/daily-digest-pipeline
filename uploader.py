"""
アップローダモジュール
生成したMarkdownをNotion APIでMCPログページに全文置換で書き込む。
"""

import logging
import time
from typing import Any
import requests

from notion_client import Client, APIResponseError

import config

logger = logging.getLogger(__name__)

# リトライ設定
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒


def _device_filter() -> dict[str, Any]:
    """この端末のページだけに絞る Notion のフィルタ。"""
    return {"property": "端末", "select": {"equals": config.DEVICE_NAME}}


def _page_title(target_date: str) -> str:
    """ページタイトル。Win は従来の形のまま、それ以外は端末名を付ける。"""
    if config.DEVICE_NAME == "Win":
        return f"Daily Digest {target_date}"
    return f"Daily Digest {target_date} ({config.DEVICE_NAME})"


def _page_properties(target_date: str) -> dict[str, Any]:
    """作成・上書きで共通のページプロパティ。"""
    return {
        "Title": {"title": [{"text": {"content": _page_title(target_date)}}]},
        "Date": {"date": {"start": target_date}},
        "端末": {"select": {"name": config.DEVICE_NAME}},
        "AI Summary Generated": {"checkbox": False},
    }


def _find_page_id_by_date(db_id: str, target_date: str) -> str | None:
    """この端末の対象日の既存ページIDを取得する。存在しない場合はNone。"""
    headers = {
        "Authorization": f"Bearer {config.NOTION_API_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    url = f"https://api.notion.com/v1/databases/{db_id}/query"
    payload = {
        "filter": {
            "and": [
                {"property": "Date", "date": {"equals": target_date}},
                _device_filter(),
            ]
        },
        "page_size": 1,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        return None
    return results[0]["id"]


def page_exists(target_date: str) -> bool:
    """
    この端末の対象日のページがNotionデータベースにあるかを返す。

    Args:
        target_date: 対象日の文字列（例: '2026-04-10'）

    Returns:
        ページがあればTrue

    Raises:
        requests.RequestException: Notion APIへの問い合わせに失敗した場合
    """
    return _find_page_id_by_date(config.MCP_LOG_DB_ID, target_date) is not None


def _replace_page_children(
    notion: Client, page_id: str, blocks: list[dict[str, Any]]
) -> None:
    """ページ配下の既存ブロックを削除し、新しいブロックで置換する。"""
    start_cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id, "page_size": 100}
        if start_cursor:
            kwargs["start_cursor"] = start_cursor
        children = notion.blocks.children.list(**kwargs)

        for child in children.get("results", []):
            notion.blocks.delete(block_id=child["id"])

        if not children.get("has_more"):
            break
        start_cursor = children.get("next_cursor")

    if not blocks:
        return

    chunk_size = 100
    for start in range(0, len(blocks), chunk_size):
        chunk = blocks[start : start + chunk_size]
        notion.blocks.children.append(
            block_id=page_id,
            children=chunk,
        )


def _markdown_to_notion_blocks(markdown: str) -> list[dict[str, Any]]:
    """
    Markdown文字列をNotion APIのブロック形式に変換する。

    対応フォーマット:
        - ## → heading_2
        - ### → heading_3
        - テーブル（| ... |）→ table
        - - [リンク](URL) → bulleted_list_item with link
        - 数字. テキスト → numbered_list_item
        - --- → divider
        - *イタリック* → paragraph with italic
        - 通常テキスト → paragraph
    """
    lines = markdown.split("\n")
    blocks: list[dict[str, Any]] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # 空行はスキップ
        if not line.strip():
            i += 1
            continue

        # === 水平線 ===
        if line.strip() == "---":
            blocks.append({"type": "divider", "divider": {}})
            i += 1
            continue

        # === 見出し2 ===
        if line.startswith("## "):
            text = line[3:]
            blocks.append(_heading_block(2, text))
            i += 1
            continue

        # === 見出し3 ===
        if line.startswith("### "):
            text = line[4:]
            blocks.append(_heading_block(3, text))
            i += 1
            continue

        # === テーブル ===
        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            blocks.append(_table_block(table_lines))
            continue

        # === 太字テキスト行（**...**） ===
        if line.startswith("**") and line.endswith("**"):
            blocks.append(_paragraph_block(line, bold=True))
            i += 1
            continue

        # === 箇条書き（- で始まる） ===
        if line.startswith("- "):
            text = line[2:]
            blocks.append(_bulleted_list_item(text))
            i += 1
            continue

        # === 番号付きリスト ===
        if len(line) > 2 and line[0].isdigit() and ". " in line[:5]:
            dot_pos = line.index(". ")
            text = line[dot_pos + 2 :]
            blocks.append(_numbered_list_item(text))
            i += 1
            continue

        # === 通常のパラグラフ ===
        blocks.append(_paragraph_block(line))
        i += 1

    return blocks


def _parse_rich_text(text: str) -> list[dict[str, Any]]:
    """
    テキスト内のMarkdownリンクやボールド等をNotion rich_textに変換する。
    """
    import re

    rich_text: list[dict[str, Any]] = []
    # マークダウンリンクを検出: [text](url)
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    last_end = 0

    for match in re.finditer(pattern, text):
        # リンク前のテキスト
        if match.start() > last_end:
            before = text[last_end : match.start()]
            if before:
                rich_text.append(_text_obj(before))

        # リンク
        link_text = match.group(1)
        link_url = match.group(2)
        rich_text.append(_text_obj(link_text, link=link_url))
        last_end = match.end()

    # 残りのテキスト
    remaining = text[last_end:]
    if remaining:
        # イタリック（*...*）を処理
        if remaining.startswith("*") and remaining.endswith("*"):
            rich_text.append(_text_obj(remaining[1:-1], italic=True))
        else:
            rich_text.append(_text_obj(remaining))

    if not rich_text:
        rich_text.append(_text_obj(text))

    return rich_text


def _text_obj(
    text: str,
    bold: bool = False,
    italic: bool = False,
    link: str | None = None,
) -> dict[str, Any]:
    """Notion rich_text オブジェクトを生成する。"""
    # ボールド記法（**...**）を解除
    if text.startswith("**") and text.endswith("**"):
        text = text[2:-2]
        bold = True

    obj: dict[str, Any] = {
        "type": "text",
        "text": {"content": text},
        "annotations": {
            "bold": bold,
            "italic": italic,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    }
    if link:
        obj["text"]["link"] = {"url": link}
    return obj


def _heading_block(level: int, text: str) -> dict[str, Any]:
    """見出しブロックを生成する。"""
    key = f"heading_{level}"
    return {
        "type": key,
        key: {"rich_text": _parse_rich_text(text)},
    }


def _paragraph_block(text: str, bold: bool = False) -> dict[str, Any]:
    """パラグラフブロックを生成する。"""
    if bold:
        return {
            "type": "paragraph",
            "paragraph": {"rich_text": [_text_obj(text, bold=True)]},
        }
    return {
        "type": "paragraph",
        "paragraph": {"rich_text": _parse_rich_text(text)},
    }


def _bulleted_list_item(text: str) -> dict[str, Any]:
    """箇条書きブロックを生成する。"""
    return {
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _parse_rich_text(text)},
    }


def _numbered_list_item(text: str) -> dict[str, Any]:
    """番号付きリストブロックを生成する。"""
    return {
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _parse_rich_text(text)},
    }


def _table_block(table_lines: list[str]) -> dict[str, Any]:
    """テーブルブロックを生成する。"""
    rows: list[list[str]] = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        # 区切り行（---|---）をスキップ
        if all(set(c) <= {"-", ":"} for c in cells):
            continue
        rows.append(cells)

    if not rows:
        return _paragraph_block("（空テーブル）")

    col_count = len(rows[0])

    table_rows = []
    for row in rows:
        # セル数を合わせる
        while len(row) < col_count:
            row.append("")
        table_rows.append(
            {
                "type": "table_row",
                "table_row": {
                    "cells": [[_text_obj(cell)] for cell in row[:col_count]],
                },
            }
        )

    return {
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


def get_latest_processed_date() -> str | None:
    """
    Notionのデータベースから、この端末で一番最後に作成されたログの日付を取得する。
    """
    if not config.NOTION_API_TOKEN or not config.MCP_LOG_DB_ID:
        logger.warning("NOTION_API_TOKEN または MCP_LOG_DB_ID が設定されていません。")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {config.NOTION_API_TOKEN}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }
        url = f"https://api.notion.com/v1/databases/{config.MCP_LOG_DB_ID}/query"
        payload = {
            "filter": _device_filter(),
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 1,
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()

        results = resp.json().get("results", [])
        if not results:
            return None

        latest_page = results[0]
        properties = latest_page.get("properties", {})
        date_prop = properties.get("Date", {})

        if date_prop.get("type") == "date" and date_prop.get("date"):
            return date_prop["date"].get("start")

        return None

    except Exception as e:
        logger.error(f"Notion DBからの最新日付取得に失敗しました: {e}")
        return None


def upload(markdown: str, target_date: str, dry_run: bool = False) -> bool:
    """
    MCPログをNotionデータベースの新規ページとして作成する。

    Args:
        markdown: MCPログ形式のMarkdown文字列
        target_date: 対象日の文字列（例: '2026-04-10'）
        dry_run: Trueの場合、Notion更新を行わずMarkdownを標準出力に表示

    Returns:
        成功した場合True
    """
    if dry_run:
        logger.info(f"=== DRY RUN モード: {target_date} ===")
        print(markdown)
        return True

    if not config.NOTION_API_TOKEN or not config.MCP_LOG_DB_ID:
        logger.error("NOTION_API_TOKEN または MCP_LOG_DB_ID が設定されていません。")
        return False

    db_id = config.MCP_LOG_DB_ID

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            notion = Client(auth=config.NOTION_API_TOKEN)

            # 1. Markdownをブロックに変換
            blocks = _markdown_to_notion_blocks(markdown)
            logger.info(f"{len(blocks)}個のブロックを作成中... ({target_date})")

            existing_page_id = _find_page_id_by_date(db_id, target_date)
            if existing_page_id:
                # 既存ページを上書き更新
                notion.pages.update(
                    page_id=existing_page_id,
                    properties=_page_properties(target_date),
                )
                _replace_page_children(notion, existing_page_id, blocks)
                logger.info(f"既存ページを上書き更新しました（{target_date}）")
                return True

            # 2. Notion APIでページを新規作成
            # 1回のリクエストで最大100ブロックまで送信可能
            initial_blocks = blocks[:100]
            remaining_blocks = blocks[100:]

            new_page = notion.pages.create(
                parent={"database_id": db_id},
                properties=_page_properties(target_date),
                children=initial_blocks,
            )

            page_id = new_page["id"]

            # 3. 100ブロックを超える場合は追加書き込み
            if remaining_blocks:
                chunk_size = 100
                for start in range(0, len(remaining_blocks), chunk_size):
                    chunk = remaining_blocks[start : start + chunk_size]
                    notion.blocks.children.append(
                        block_id=page_id,
                        children=chunk,
                    )

            logger.info(
                f"Notionデータベースへの新規追加が完了しました（{target_date}）"
            )
            return True

        except APIResponseError as e:
            if e.status == 429 and attempt < MAX_RETRIES:
                # レートリミット。待機して再試行
                wait = RETRY_DELAY * attempt
                logger.warning(
                    f"レートリミット。{wait}秒待機して再試行（{attempt}/{MAX_RETRIES}）"
                )
                time.sleep(wait)
            else:
                logger.error(f"Notion API エラー: {e}")
                return False
        except Exception as e:
            logger.error(f"アップロード中にエラーが発生しました: {e}")
            return False

    return False
