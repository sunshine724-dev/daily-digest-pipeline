"""
フォーマッタモジュールのユニットテスト
"""

from formatter import (
    format_digest,
    format_duration,
    format_timeline_line,
    generate_highlights,
)


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


def _slot(start, *apps):
    return {
        "start": start,
        "apps": [
            {"app_name": name, "duration_seconds": seconds, "title": title}
            for name, seconds, title in apps
        ],
    }


class TestFormatTimelineLine:
    """15分の時間帯1行の書き方のテスト"""

    def test_shows_top_apps_and_folds_rest(self):
        """上位3つを分数つきで出し、残りを「他」にまとめ、.exe を外すこと"""
        line = format_timeline_line(_slot(
            "10:45",
            ("Code.exe", 540, None),
            ("chrome.exe", 240, "juice-shop/juice-shop - Google Chrome"),
            ("WindowsTerminal.exe", 60, None),
            ("Discord.exe", 50, None),
            ("SearchHost.exe", 40, None),
        ))

        assert line == (
            "10:45 Code 9m, chrome 4m（juice-shop/juice-shop）, WindowsTerminal 1m, 他 2m"
        )

    def test_skips_apps_under_one_minute(self):
        """1分未満のアプリは載せず、全部1分未満なら行を出さないこと"""
        assert format_timeline_line(_slot("06:15", ("explorer.exe", 29, None))) is None
        assert (
            format_timeline_line(_slot("06:30", ("Code.exe", 120, None), ("explorer.exe", 20, None)))
            == "06:30 Code 2m"
        )

    def test_truncates_long_title(self):
        """長いページ名は40字で切ること"""
        line = format_timeline_line(_slot("09:00", ("chrome.exe", 600, "あ" * 50)))

        assert line == "09:00 chrome 10m（" + "あ" * 40 + "…）"


class TestFormatDigestTimeline:
    """format_digest の時間帯の節のテスト"""

    def test_timeline_section_is_toggle_before_footer(self):
        """時間帯の節を折りたたみ見出しでフッターの前に出すこと"""
        result = format_digest(
            [], [], [], [],
            timeline=[
                _slot("09:00", ("Code.exe", 600, None)),
                _slot("09:15", ("explorer.exe", 10, None)),
            ],
        )

        lines = result.split("\n")
        heading = lines.index("### ▶ 🕒 Timeline（15分・JST）")
        assert lines[heading + 1] == "- 09:00 Code 10m"
        assert lines[heading + 2] == ""
        assert heading < lines.index("---")

    def test_no_timeline_section_without_data(self):
        """時間帯のデータが無ければ節を出さないこと"""
        assert "Timeline" not in format_digest([], [], [], [])
