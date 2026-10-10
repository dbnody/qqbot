"""AI 对话记忆的隔离存储。

scope_id 是严格的数据边界：group:<群号>、private:<QQ号> 各自独立，
读取某个 scope 时不会查询其他群或其他私聊用户的数据。
"""

from __future__ import annotations

from app.database import get_connection


def load_ai_memory(scope_id: str, limit: int = 8) -> list[dict[str, str]]:
    """读取当前会话最近的消息，最多返回 limit 条。"""
    limit = max(0, min(limit, 20))
    if limit == 0:
        return []
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT role, content FROM ai_memories
            WHERE scope_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (str(scope_id), limit),
        ).fetchall()
    return [{"role": str(row["role"]), "content": str(row["content"])} for row in reversed(rows)]


def append_ai_memory(scope_id: str, role: str, content: str) -> None:
    """追加一条会话消息，并限制每个 scope 的长期记录数量。"""
    if role not in {"user", "assistant"}:
        return
    content = str(content).strip()[:4000]
    if not content:
        return
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO ai_memories (scope_id, role, content) VALUES (?, ?, ?)",
            (str(scope_id), role, content),
        )
        connection.execute(
            """
            DELETE FROM ai_memories
            WHERE scope_id = ? AND id NOT IN (
                SELECT id FROM ai_memories WHERE scope_id = ? ORDER BY id DESC LIMIT 40
            )
            """,
            (str(scope_id), str(scope_id)),
        )


def clear_ai_memory(scope_id: str) -> None:
    """清除当前群或当前私聊用户的 AI 记忆。"""
    with get_connection() as connection:
        connection.execute("DELETE FROM ai_memories WHERE scope_id = ?", (str(scope_id),))
