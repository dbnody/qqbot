"""AI 记忆模型：短期对话窗口 + 滚动摘要 + 事实库。

scope_id 是严格的数据边界：group:<群号>、private:<QQ号> 各自独立。
三层结构：
1. ai_memories —— 最近若干轮原文，直接进上下文；
2. ai_summaries —— 每积累 N 条消息，把旧消息压成一段摘要；
3. ai_facts —— 从对话里抽出的长期事实，按关键词相关度召回后注入。
"""

from __future__ import annotations

import json
import os
import re

from app.database import get_connection


RECENT_LIMIT = 10
KEEP_RAW = 6


def _summary_every() -> int:
    try:
        return max(4, int(os.getenv("MEMORY_SUMMARY_EVERY", "20")))
    except ValueError:
        return 20


def load_ai_memory(scope_id: str, limit: int = RECENT_LIMIT) -> list[dict[str, str]]:
    """读取当前会话最近的消息，最多返回 limit 条。"""
    limit = max(0, min(limit, 20))
    if limit == 0:
        return []
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT role, content FROM ai_memories WHERE scope_id = ? ORDER BY id DESC LIMIT ?",
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
                SELECT id FROM ai_memories WHERE scope_id = ? ORDER BY id DESC LIMIT 60
            )
            """,
            (str(scope_id), str(scope_id)),
        )


def clear_ai_memory(scope_id: str) -> None:
    """清除当前群或当前私聊用户的全部 AI 记忆。"""
    scope_id = str(scope_id)
    with get_connection() as connection:
        for table in ("ai_memories", "ai_summaries", "ai_facts"):
            connection.execute(f"DELETE FROM {table} WHERE scope_id = ?", (scope_id,))


def get_summary(scope_id: str) -> tuple[str, int]:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT summary, upto_id FROM ai_summaries WHERE scope_id = ?",
            (str(scope_id),),
        ).fetchone()
    return (str(row["summary"]), int(row["upto_id"])) if row else ("", 0)


def _save_summary(scope_id: str, summary: str, upto_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_summaries (scope_id, summary, upto_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET summary = excluded.summary,
                upto_id = excluded.upto_id, updated_at = CURRENT_TIMESTAMP
            """,
            (str(scope_id), summary[:2000], int(upto_id)),
        )


def add_fact(scope_id: str, content: str) -> bool:
    content = re.sub(r"\s+", " ", str(content)).strip()[:300]
    if len(content) < 2:
        return False
    with get_connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM ai_facts WHERE scope_id = ? AND content = ?",
            (str(scope_id), content),
        ).fetchone()
        if exists:
            return False
        connection.execute(
            "INSERT INTO ai_facts (scope_id, content) VALUES (?, ?)",
            (str(scope_id), content),
        )
        connection.execute(
            """
            DELETE FROM ai_facts
            WHERE scope_id = ? AND id NOT IN (
                SELECT id FROM ai_facts WHERE scope_id = ? ORDER BY id DESC LIMIT 200
            )
            """,
            (str(scope_id), str(scope_id)),
        )
    return True


def _grams(text: str) -> set[str]:
    """中文按 2 字切块，英文/数字按词切块，够用且零依赖。"""
    text = text.lower()
    grams = set(re.findall(r"[a-z0-9_]{2,}", text))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", text):
        grams.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
        if len(chunk) == 1:
            grams.add(chunk)
    return grams


def recall_facts(scope_id: str, query: str = "", limit: int = 8) -> list[str]:
    """按关键词相关度召回记忆事实，query 为空时取最近的。"""
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT content, id FROM ai_facts WHERE scope_id = ? ORDER BY id DESC LIMIT 200",
            (str(scope_id),),
        ).fetchall()
    if not rows:
        return []
    grams = sorted(_grams(query))[:40]
    contents = [str(row["content"]) for row in rows]
    if grams:
        # 越少见的词权重越高，避免“喜欢”这类高频词把结果带偏。
        weights = {gram: 1 / max(1, sum(gram in text.lower() for text in contents)) for gram in grams}
    else:
        weights = {}
    scored: list[tuple[float, int, str]] = []
    for row in rows:
        content = str(row["content"])
        if not grams:
            scored.append((0.0, int(row["id"]), content))
            continue
        score = sum(weights[gram] for gram in grams if gram in content.lower())
        if score:
            scored.append((score, int(row["id"]), content))
    if not scored:
        scored = [(0.0, int(row["id"]), str(row["content"])) for row in rows[:limit]]
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [content for _, _, content in scored[: max(1, limit)]]


def all_facts(scope_id: str, limit: int = 30) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT content FROM ai_facts WHERE scope_id = ? ORDER BY id DESC LIMIT ?",
            (str(scope_id), limit),
        ).fetchall()
    return [str(row["content"]) for row in rows]


def unsynced_messages(scope_id: str) -> list[dict[str, object]]:
    summary, upto_id = get_summary(scope_id)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, role, content FROM ai_memories WHERE scope_id = ? AND id > ? ORDER BY id",
            (str(scope_id), upto_id),
        ).fetchall()
    return [{"id": int(r["id"]), "role": str(r["role"]), "content": str(r["content"])} for r in rows]


_CONSOLIDATE_SYSTEM = (
    "你是记忆整理器。把给定的聊天记录压缩成一段不超过 200 字的中文摘要，"
    "并抽取值得长期记住的稳定事实（称呼、身份、喜好、关系、约定、重要事件等）。"
    '只输出 JSON：{"summary": "...", "facts": ["...", "..."]}，不要输出其它内容。'
)


def _parse_json_payload(raw: str) -> dict[str, object]:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("模型没有返回 JSON")
    payload = json.loads(raw[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("JSON 结构不正确")
    return payload


async def consolidate(scope_id: str, *, force: bool = False) -> bool:
    """消息攒够一批后压缩成摘要并抽取事实；返回是否真的执行了压缩。"""
    # 延迟导入，避免记忆模块与网络客户端循环依赖。
    from app.ai_client import chat

    rows = unsynced_messages(scope_id)
    every = _summary_every()
    if not force and len(rows) < every:
        return False
    chunk = rows[:-KEEP_RAW] if len(rows) > KEEP_RAW else rows[:]
    if not chunk:
        return False

    old_summary, _ = get_summary(scope_id)
    transcript = "\n".join(f"{item['role']}: {str(item['content'])[:500]}" for item in chunk[-40:])
    prompt = f"已有摘要：{old_summary or '无'}\n新的聊天记录：\n{transcript}\n请合并成新的摘要。"
    try:
        raw = await chat(
            [
                {"role": "system", "content": _CONSOLIDATE_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        payload = _parse_json_payload(raw)
    except Exception:
        return False

    summary = str(payload.get("summary") or "").strip()
    if summary:
        _save_summary(scope_id, summary, int(chunk[-1]["id"]))  # type: ignore[arg-type]
    facts = payload.get("facts")
    if isinstance(facts, list):
        for fact in facts[:8]:
            add_fact(scope_id, str(fact))
    return True


def memory_overview(scope_id: str) -> str:
    summary, _ = get_summary(scope_id)
    facts = all_facts(scope_id, 10)
    lines = [f"摘要：{summary}" if summary else "摘要：暂无（聊得再多一点会自动生成）"]
    if facts:
        lines.append("记住的事：\n" + "\n".join(f"・{fact}" for fact in facts))
    else:
        lines.append("记住的事：暂无")
    return "\n".join(lines)


def memory_block(scope_id: str, query: str) -> str:
    """生成注入 system prompt 的记忆片段。"""
    summary, _ = get_summary(scope_id)
    facts = recall_facts(scope_id, query)
    parts = []
    if summary:
        parts.append(f"【你们之前聊过的（摘要）】{summary}")
    if facts:
        parts.append("【需要记住的信息】\n" + "\n".join(f"・{fact}" for fact in facts))
    return "\n".join(parts)
