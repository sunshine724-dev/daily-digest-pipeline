"""
uploader モジュールのテスト
端末ごとにページを分ける振る舞いを検証する。
"""

from unittest.mock import MagicMock, patch

import config
import uploader


class TestPageProperties:
    """ページプロパティのテスト"""

    def test_win_title_keeps_legacy_format(self, monkeypatch):
        monkeypatch.setattr(config, "DEVICE_NAME", "Win")

        props = uploader._page_properties("2026-10-03")

        assert props["Title"]["title"][0]["text"]["content"] == "Daily Digest 2026-10-03"
        assert props["端末"] == {"select": {"name": "Win"}}

    def test_mac_title_has_device_suffix(self, monkeypatch):
        monkeypatch.setattr(config, "DEVICE_NAME", "Mac")

        props = uploader._page_properties("2026-10-03")

        assert (
            props["Title"]["title"][0]["text"]["content"]
            == "Daily Digest 2026-10-03 (Mac)"
        )
        assert props["端末"] == {"select": {"name": "Mac"}}


class TestDeviceScopedQueries:
    """Notion への問い合わせが端末で絞られていることのテスト"""

    @patch("uploader.requests")
    def test_find_page_filters_by_date_and_device(self, mock_requests, monkeypatch):
        monkeypatch.setattr(config, "DEVICE_NAME", "Mac")
        mock_requests.post.return_value = MagicMock(
            json=MagicMock(return_value={"results": [{"id": "page-mac"}]})
        )

        page_id = uploader._find_page_id_by_date("db", "2026-10-03")

        payload = mock_requests.post.call_args.kwargs["json"]
        assert payload["filter"] == {
            "and": [
                {"property": "Date", "date": {"equals": "2026-10-03"}},
                {"property": "端末", "select": {"equals": "Mac"}},
            ]
        }
        assert page_id == "page-mac"

    @patch("uploader.requests")
    def test_latest_date_filters_by_device(self, mock_requests, monkeypatch):
        monkeypatch.setattr(config, "DEVICE_NAME", "Win")
        monkeypatch.setattr(config, "NOTION_API_TOKEN", "token")
        monkeypatch.setattr(config, "MCP_LOG_DB_ID", "db")
        mock_requests.post.return_value = MagicMock(
            json=MagicMock(
                return_value={
                    "results": [
                        {
                            "properties": {
                                "Date": {"type": "date", "date": {"start": "2026-10-02"}}
                            }
                        }
                    ]
                }
            )
        )

        latest = uploader.get_latest_processed_date()

        payload = mock_requests.post.call_args.kwargs["json"]
        assert payload["filter"] == {"property": "端末", "select": {"equals": "Win"}}
        assert latest == "2026-10-02"


class TestToggleHeading:
    """折りたたみ見出しへの変換のテスト"""

    def test_toggle_heading_contains_following_bullets_as_plain_text(self):
        markdown = "\n".join([
            "### ▶ 🕒 Timeline（15分・JST）",
            "- 09:00 chrome 5m（[PR] fix (#12)）",
            "- 09:15 Code 10m",
            "",
            "---",
        ])

        blocks = uploader._markdown_to_notion_blocks(markdown)

        assert [b["type"] for b in blocks] == ["heading_3", "divider"]
        heading = blocks[0]["heading_3"]
        assert heading["is_toggleable"] is True
        assert heading["rich_text"][0]["text"]["content"] == "🕒 Timeline（15分・JST）"
        contents = [
            child["bulleted_list_item"]["rich_text"][0]["text"]["content"]
            for child in heading["children"]
        ]
        assert contents == ["09:00 chrome 5m（[PR] fix (#12)）", "09:15 Code 10m"]
        assert "link" not in heading["children"][0]["bulleted_list_item"]["rich_text"][0]["text"]

    def test_toggle_children_are_capped(self):
        markdown = "\n".join(["### ▶ T"] + [f"- {i}" for i in range(105)])

        blocks = uploader._markdown_to_notion_blocks(markdown)

        assert len(blocks[0]["heading_3"]["children"]) == 100

    def test_plain_heading_is_not_toggle(self):
        blocks = uploader._markdown_to_notion_blocks("### ⏱ Time Tracking")

        assert "is_toggleable" not in blocks[0]["heading_3"]
class TestPageExists:
    """対象日のページ有無の判定のテスト"""

    @patch("uploader._find_page_id_by_date", return_value="page-mac")
    def test_true_when_page_found(self, find_page, monkeypatch):
        monkeypatch.setattr(config, "MCP_LOG_DB_ID", "db")

        assert uploader.page_exists("2026-10-04") is True
        find_page.assert_called_once_with("db", "2026-10-04")

    @patch("uploader._find_page_id_by_date", return_value=None)
    def test_false_when_page_missing(self, find_page):
        assert uploader.page_exists("2026-10-04") is False
