"""语音聊天模式：按 scope（群 / 私聊）记住「一直用语音回」的状态。

用户说「陪我语音聊会」就打开，说到「打字吧 / 用文字」才关掉。
"""

from __future__ import annotations

from app.database import get_connection


def is_voice_mode(scope_id: str) -> bool:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT enabled FROM ai_voice_modes WHERE scope_id = ?", (str(scope_id),)
        ).fetchone()
    return bool(row and row[0])


def set_voice_mode(scope_id: str, enabled: bool) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_voice_modes (scope_id, enabled, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET
                enabled = excluded.enabled, updated_at = CURRENT_TIMESTAMP
            """,
            (str(scope_id), 1 if enabled else 0),
        )
