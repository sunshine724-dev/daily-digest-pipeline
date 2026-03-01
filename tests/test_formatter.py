"""
フォーマッタモジュールのユニットテスト
"""

import pytest
from formatter import format_digest, format_duration, generate_highlights


class TestFormatDuration:
    """format_duration のテスト"""

    def test_hours_and_minutes(self):
        assert format_duration(5400) == "1h 30m"

    def test_only_minutes(self):
        assert format_duration(300) == "5m"

    def test_zero(self):
        assert format_duration(0) == "0m"

    def test_large_duration(self):
        assert format_duration(36000) == "10h 00m"


class TestGenerateHighlights:
    """generate_highlights のテスト"""

    def test_max_five_highlights(self):
        """ハイライトは最大5つまで"""
        notion = [{"title": f"page{i}", "url": f"url{i}", "last_edited": ""} for i in range(10)]
        github = [
            {"repo_name": f"user/repo{i}", "commits": i + 1, "commit_messages": [f"msg{i}"], "repo_url": f"url{i}"}
            for i in range(5)
        ]
        chrome = [{"title": f"site{i}", "url": f"url{i}", "visit_count": i + 1} for i in range(5)]
        aw = [{"app_name": f"app{i}", "duration_seconds": (i + 1) * 3600} for i in range(5)]

        highlights = generate_highlights(notion, github, chrome, aw)
        assert len(highlights) <= 5

    def test_empty_data(self):
        """空データでも例外が発生しないこと"""
        highlights = generate_highlights([], [], [], [])
        assert isinstance(highlights, list)
        assert len(highlights) == 0


class TestFormatDigest:
    """format_digest のテスト"""

    def test_basic_format(self):
        """基本的なフォーマットが正しいこと"""
        notion = [{"title": "テスト", "url": "https://notion.so/test", "last_edited": "2026-03-01"}]
        github = [{"repo_name": "user/repo", "commits": 3, "commit_messages": ["テスト追加"], "repo_url": "https://github.com/user/repo"}]
        chrome = [{"title": "GitHub", "url": "https://github.com", "visit_count": 10}]
        aw = [{"app_name": "VS Code", "duration_seconds": 7200}]

        result = format_digest(notion, github, chrome, aw)

        # 必須セクションの存在確認
        assert "Daily Digest" in result
        assert "Highlights" in result
        assert "Links" in result
        assert "Notion" in result
        assert "GitHub" in result
        assert "Time Tracking" in result
        assert "Chrome Top Sites" in result

    def test_empty_data_no_error(self):
        """すべてのデータが空でもエラーにならないこと"""
        result = format_digest([], [], [], [])
        assert "Daily Digest" in result
        assert "アクティビティなし" in result
