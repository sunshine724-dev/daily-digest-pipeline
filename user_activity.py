"""
ユーザー操作の有無を判定するモジュール
macOS の IOHIDSystem が持つ「最後の入力からの経過時間」を読む。
"""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)

_HID_IDLE_TIME_PATTERN = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def get_idle_seconds() -> float | None:
    """
    最後にキーボード・マウスが操作されてからの秒数を返す。

    macOS の `ioreg` から HIDIdleTime（ナノ秒）を読む。
    スリープ中の DarkWake で起動された場合も、この値は大きいままになる。

    Returns:
        経過秒数。macOS 以外や読み取りに失敗した場合は None
    """
    try:
        result = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem", "-d", "4"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning(f"操作なし時間の取得に失敗しました: {e}")
        return None

    match = _HID_IDLE_TIME_PATTERN.search(result.stdout)
    if not match:
        logger.warning("ioreg の出力に HIDIdleTime が見つかりませんでした。")
        return None
    return int(match.group(1)) / 1_000_000_000
