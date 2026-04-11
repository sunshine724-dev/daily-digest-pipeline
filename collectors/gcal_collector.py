"""
Google Calendar収集モジュール
Google Calendar APIを使用して、今日の予定一覧を取得する。

初回実行時にブラウザでGoogleアカウント認証が必要。
認証後は token.json に保存され、以降は自動更新される。

セットアップ手順:
  1. Google Cloud Console (https://console.cloud.google.com/) でプロジェクトを作成
  2. Google Calendar API を有効化
  3. OAuth 2.0 クライアントIDを作成（デスクトップアプリ）
  4. credentials.json をダウンロードしてプロジェクトルートに配置
  5. 初回実行時にブラウザ認証を完了
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import TypedDict

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# 読み取り専用スコープ
_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# 認証ファイルのパス（プロジェクトルート）
_PROJECT_ROOT = Path(__file__).parent.parent
_CREDENTIALS_PATH = _PROJECT_ROOT / "credentials.json"
_TOKEN_PATH = _PROJECT_ROOT / "token.json"


class CalendarEventInfo(TypedDict):
    """カレンダーイベント情報"""
    summary: str
    start_time: str
    end_time: str
    is_all_day: bool


def _get_credentials() -> Credentials | None:
    """
    OAuth2認証情報を取得する。
    token.json が存在すれば読み込み、期限切れなら更新。
    なければ credentials.json からブラウザ認証を開始。
    """
    creds = None

    # 保存済みトークンがあれば読み込み
    if _TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_PATH), _SCOPES)

    # トークンが無効または期限切れ
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # トークンを更新
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"トークン更新に失敗しました: {e}")
                return None
        else:
            # 新規認証（ブラウザが開く）
            if not _CREDENTIALS_PATH.exists():
                logger.warning(
                    f"credentials.json が見つかりません: {_CREDENTIALS_PATH}\n"
                    "Google Cloud Console からダウンロードしてください。"
                )
                return None

            flow = InstalledAppFlow.from_client_secrets_file(
                str(_CREDENTIALS_PATH), _SCOPES
            )
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(_TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    return creds


def collect(target_date_str: str) -> list[CalendarEventInfo]:
    """
    指定日のGoogleカレンダーイベントを取得する。

    Returns:
        CalendarEventInfoのリスト（開始時刻順）
    """
    creds = _get_credentials()
    if not creds:
        logger.warning("Google Calendar の認証情報がありません。スキップします。")
        return []

    try:
        service = build("calendar", "v3", credentials=creds)

        # 対象日の開始・終了時刻（JST）
        jst = timezone(timedelta(hours=9))
        dt = datetime.strptime(target_date_str, "%Y-%m-%d").replace(tzinfo=jst)
        target_start = dt
        target_end = target_start + timedelta(days=1)

        # イベント取得
        events_result = service.events().list(
            calendarId="primary",
            timeMin=target_start.isoformat(),
            timeMax=target_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = events_result.get("items", [])
        results: list[CalendarEventInfo] = []

        for event in events:
            summary = event.get("summary", "（タイトルなし）")

            # 終日イベントか時間指定イベントかを判定
            start = event.get("start", {})
            end = event.get("end", {})

            if "date" in start:
                # 終日イベント
                results.append(CalendarEventInfo(
                    summary=summary,
                    start_time=start["date"],
                    end_time=end.get("date", ""),
                    is_all_day=True,
                ))
            else:
                # 時間指定イベント
                start_dt = start.get("dateTime", "")
                end_dt = end.get("dateTime", "")

                # 表示用に時刻のみ抽出
                start_display = ""
                end_display = ""
                if start_dt:
                    try:
                        dt = datetime.fromisoformat(start_dt)
                        start_display = dt.strftime("%H:%M")
                    except ValueError:
                        start_display = start_dt
                if end_dt:
                    try:
                        dt = datetime.fromisoformat(end_dt)
                        end_display = dt.strftime("%H:%M")
                    except ValueError:
                        end_display = end_dt

                results.append(CalendarEventInfo(
                    summary=summary,
                    start_time=start_display,
                    end_time=end_display,
                    is_all_day=False,
                ))

        logger.info(f"Google Calendar: {len(results)}件のイベントを取得しました。")
        return results

    except Exception as e:
        logger.error(f"Google Calendar収集でエラーが発生しました: {e}")
        return []
