"""
WhatPulse収集モジュール
WhatPulse Client API（ローカル）から入力デバイス・ネットワーク統計データを取得する。

WhatPulseクライアントの「Client API」が有効になっている必要がある。
デフォルトポート: 3490
"""

import logging
from typing import TypedDict

import requests

import config

logger = logging.getLogger(__name__)


class WhatPulseStats(TypedDict):
    """WhatPulse統計データ"""
    keys: int                # キーボード打鍵数
    clicks: int              # マウスクリック数
    scrolls: int             # スクロール数
    download_mb: float       # ダウンロード量（MB）
    upload_mb: float         # アップロード量（MB）
    uptime_seconds: int      # 稼働時間（秒）


def collect(target_date_str: str = "") -> WhatPulseStats | None:
    """
    WhatPulse Client APIから統計データを取得する。

    WhatPulseのローカルAPIは日別フィルタリングを直接サポートしていないため、
    /v1/unpulsed（最後のパルス以降の統計）を取得する。
    日次パイプライン実行後にパルスすることで、1日分のデータとして扱える。

    Args:
        target_date_str: YYYY-MM-DD形式の日付文字列（現在は未使用、将来の拡張用）

    Returns:
        WhatPulseStatsの辞書、または取得失敗時はNone
    """
    base_url = config.WHATPULSE_API_BASE.rstrip("/")

    try:
        # unpulsed統計を取得（最後のパルス以降のローカルデータ）
        unpulsed_url = f"{base_url}/v1/unpulsed"
        resp = requests.get(unpulsed_url, timeout=5)
        resp.raise_for_status()
        data = resp.json()

        # レスポンスからデータを抽出
        keys = int(data.get("keys", 0))
        clicks = int(data.get("clicks", 0))
        scrolls = int(data.get("scrolls", 0))

        # download/uploadはバイト単位で返されるのでMBに変換
        download_bytes = float(data.get("download", 0))
        upload_bytes = float(data.get("upload", 0))
        download_mb = download_bytes / (1024 * 1024)
        upload_mb = upload_bytes / (1024 * 1024)

        # 稼働時間（秒）
        uptime = int(data.get("uptime", 0))

        stats = WhatPulseStats(
            keys=keys,
            clicks=clicks,
            scrolls=scrolls,
            download_mb=round(download_mb, 2),
            upload_mb=round(upload_mb, 2),
            uptime_seconds=uptime,
        )

        logger.info(
            f"WhatPulse: keys={keys}, clicks={clicks}, scrolls={scrolls}, "
            f"DL={download_mb:.1f}MB, UL={upload_mb:.1f}MB, uptime={uptime}s"
        )
        return stats

    except requests.ConnectionError:
        logger.warning("WhatPulseに接続できません（クライアントが起動していないか、Client APIが無効です）。")
        return None
    except requests.RequestException as e:
        logger.error(f"WhatPulse APIエラー: {e}")
        return None
    except Exception as e:
        logger.error(f"WhatPulse収集でエラーが発生しました: {e}")
        return None

