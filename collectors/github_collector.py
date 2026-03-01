"""
GitHub収集モジュール
GitHub APIを使用して、今日のコミット・イベント履歴を取得する。
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import TypedDict

from github import Github, GithubException

import config

logger = logging.getLogger(__name__)


class GitHubRepoActivity(TypedDict):
    """GitHubリポジトリ別アクティビティ"""
    repo_name: str
    commits: int
    commit_messages: list[str]
    repo_url: str


def collect() -> list[GitHubRepoActivity]:
    """
    今日のGitHubアクティビティ（コミット）を取得する。

    Returns:
        GitHubRepoActivityのリスト
    """
    if not config.GITHUB_TOKEN:
        logger.warning("GITHUB_TOKEN が設定されていません。GitHub収集をスキップします。")
        return []

    if not config.GITHUB_USERNAME:
        logger.warning("GITHUB_USERNAME が設定されていません。GitHub収集をスキップします。")
        return []

    try:
        g = Github(config.GITHUB_TOKEN)

        # 今日の開始時刻（UTC）
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # ユーザーのイベントから今日のPushイベントを取得
        user = g.get_user(config.GITHUB_USERNAME)
        events = user.get_events()

        repo_activities: dict[str, GitHubRepoActivity] = {}

        for event in events:
            # イベントの日時チェック（今日より前なら終了）
            if event.created_at.replace(tzinfo=timezone.utc) < today_start:
                break

            if event.type == "PushEvent":
                repo_name = event.repo.name
                payload = event.payload

                if repo_name not in repo_activities:
                    repo_activities[repo_name] = GitHubRepoActivity(
                        repo_name=repo_name,
                        commits=0,
                        commit_messages=[],
                        repo_url=f"https://github.com/{repo_name}",
                    )

                # コミット情報を追加
                commits = payload.get("commits", [])
                repo_activities[repo_name]["commits"] += len(commits)
                for commit in commits:
                    msg = commit.get("message", "").split("\n")[0]  # 1行目のみ
                    repo_activities[repo_name]["commit_messages"].append(msg)

        results = list(repo_activities.values())[:config.MAX_GITHUB_REPOS]
        logger.info(f"GitHub: {len(results)}件のリポジトリアクティビティを取得しました。")
        return results

    except GithubException as e:
        logger.error(f"GitHub API エラー: {e}")
        return []
    except Exception as e:
        logger.error(f"GitHub収集でエラーが発生しました: {e}")
        return []
