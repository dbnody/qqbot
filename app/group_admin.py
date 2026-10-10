"""群管理权限、目标解析和违禁词处理。"""

from __future__ import annotations

import os
import re
from typing import Any

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message


def sender_role(event: GroupMessageEvent) -> str:
    return str(getattr(event.sender, "role", "member") or "member")


def is_operator_admin(event: GroupMessageEvent) -> bool:
    return sender_role(event) in {"owner", "admin"}


async def is_bot_admin(bot: Bot, group_id: int, self_id: int | str) -> bool:
    try:
        info = await bot.get_group_member_info(group_id=group_id, user_id=int(self_id))
        return str(info.get("role", "member")) in {"owner", "admin"}
    except Exception:
        return False


async def check_management_permission(bot: Bot, event: GroupMessageEvent) -> str | None:
    if not is_operator_admin(event):
        return "只有群主和群管理员可以使用群管理功能。"
    if not await is_bot_admin(bot, event.group_id, event.self_id):
        return "我目前不是本群管理员，无法执行群管理操作。"
    return None


def parse_target_and_minutes(message: Message) -> tuple[int | None, int]:
    at_targets: list[int] = []
    for segment in message:
        if segment.type != "at":
            continue
        qq = str(segment.data.get("qq", ""))
        if qq.isdigit() and qq != "all":
            at_targets.append(int(qq))

    plain_text = message.extract_plain_text()
    number_tokens = [int(item) for item in re.findall(r"\d+", plain_text)]
    target = at_targets[0] if at_targets else (number_tokens[0] if number_tokens else None)
    duration_match = re.search(
        r"(\d+)\s*(分钟|分|min|m|小时|时|hour|h|天|日|day|d)", plain_text, re.I
    )
    if duration_match:
        amount = int(duration_match.group(1))
        unit = duration_match.group(2).lower()
        if unit in {"小时", "时", "hour", "h"}:
            minutes = amount * 60
        elif unit in {"天", "日", "day", "d"}:
            minutes = amount * 24 * 60
        else:
            minutes = amount
    elif at_targets:
        minutes = number_tokens[0] if number_tokens else 1
    else:
        minutes = number_tokens[1] if len(number_tokens) > 1 else 1
    return target, max(1, min(minutes, 30 * 24 * 60))


async def protected_target_error(bot: Bot, event: GroupMessageEvent, target_id: int) -> str | None:
    if target_id == int(event.self_id):
        return "不能对我自己执行这项操作。"
    try:
        info: dict[str, Any] = await bot.get_group_member_info(
            group_id=event.group_id, user_id=target_id
        )
    except Exception:
        return "找不到这个群成员，请确认 QQ 号或 @对象正确。"
    if str(info.get("role", "member")) in {"owner", "admin"}:
        return "不能对群主或其他管理员执行这项操作。"
    return None


def forbidden_words() -> tuple[str, ...]:
    raw = os.getenv("QQBOT_FORBIDDEN_WORDS", "")
    return tuple(word.strip().lower() for word in raw.split(",") if word.strip())


def matched_forbidden_word(text: str) -> str | None:
    lowered = text.lower()
    return next((word for word in forbidden_words() if word in lowered), None)


def forbidden_mute_seconds() -> int:
    try:
        return max(0, int(os.getenv("QQBOT_FORBIDDEN_MUTE_SECONDS", "60")))
    except ValueError:
        return 60
