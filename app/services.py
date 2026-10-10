"""与聊天框架无关的业务服务。

插件只负责收取消息和回复文本，签到、修仙等规则集中在这里，便于以后迁移到 Go。
"""

from __future__ import annotations

import random
from datetime import date, datetime

from app.database import get_connection


def _save_user(user_id: str, nickname: str) -> None:
    """记录用户的最新昵称。"""
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO users (user_id, nickname)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                nickname = excluded.nickname,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, nickname),
        )


def sign_in(user_id: str, nickname: str) -> dict[str, object]:
    """执行每日签到，返回是否成功、连续信息和奖励。"""
    _save_user(user_id, nickname)
    today = date.today().isoformat()

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM sign_ins WHERE user_id = ? AND sign_date = ?",
            (user_id, today),
        ).fetchone()
        if existing:
            return {"success": False, "date": today}

        reward = random.randint(5, 20)
        connection.execute(
            "INSERT INTO sign_ins (user_id, sign_date) VALUES (?, ?)",
            (user_id, today),
        )
        total = connection.execute(
            "SELECT COUNT(*) AS count FROM sign_ins WHERE user_id = ?", (user_id,)
        ).fetchone()["count"]

    return {"success": True, "reward": reward, "total": total, "date": today}


REALMS = (
    ("炼气期", 100),
    ("筑基期", 180),
    ("金丹期", 280),
    ("元婴期", 400),
    ("化神期", 560),
    ("炼虚期", 760),
    ("合体期", 1000),
    ("大乘期", 1300),
    ("渡劫期", 0),
)


def _get_cultivator(user_id: str, nickname: str) -> dict[str, object]:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO cultivators (user_id, nickname)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET nickname = excluded.nickname
            """,
            (user_id, nickname),
        )
        row = connection.execute(
            "SELECT * FROM cultivators WHERE user_id = ?", (user_id,)
        ).fetchone()
    return dict(row)


def cultivation_profile(user_id: str, nickname: str) -> dict[str, object]:
    """返回修仙档案。"""
    row = _get_cultivator(user_id, nickname)
    realm_index = int(row["realm_index"])
    realm, threshold = REALMS[realm_index]
    return {
        "realm": realm,
        "experience": int(row["experience"]),
        "threshold": threshold,
        "spirit_stones": int(row["spirit_stones"]),
    }


def cultivate(user_id: str, nickname: str) -> dict[str, object]:
    """进行一次修炼，返回获得的经验。"""
    row = _get_cultivator(user_id, nickname)
    gain = random.randint(8, 24)
    now = datetime.now().isoformat(timespec="seconds")
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cultivators
            SET experience = experience + ?, spirit_stones = spirit_stones + 1,
                updated_at = ?
            WHERE user_id = ?
            """,
            (gain, now, user_id),
        )
        updated = connection.execute(
            "SELECT * FROM cultivators WHERE user_id = ?", (user_id,)
        ).fetchone()
    realm, threshold = REALMS[int(updated["realm_index"])]
    return {
        "gain": gain,
        "realm": realm,
        "experience": int(updated["experience"]),
        "threshold": threshold,
        "spirit_stones": int(updated["spirit_stones"]),
    }


def breakthrough(user_id: str, nickname: str) -> dict[str, object]:
    """尝试突破当前境界。"""
    row = _get_cultivator(user_id, nickname)
    current_index = int(row["realm_index"])
    current_realm, threshold = REALMS[current_index]
    if current_index >= len(REALMS) - 1:
        return {"success": False, "max_realm": True, "realm": current_realm}
    if int(row["experience"]) < threshold:
        return {
            "success": False,
            "realm": current_realm,
            "experience": int(row["experience"]),
            "threshold": threshold,
        }

    next_index = current_index + 1
    next_realm = REALMS[next_index][0]
    with get_connection() as connection:
        connection.execute(
            "UPDATE cultivators SET realm_index = ?, experience = 0, updated_at = ? WHERE user_id = ?",
            (next_index, datetime.now().isoformat(timespec="seconds"), user_id),
        )
    return {"success": True, "old_realm": current_realm, "realm": next_realm}
