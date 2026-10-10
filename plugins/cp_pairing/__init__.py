"""群内 CP 抽签。

使用 /cp 或 /群内配对在当前群随机抽取两名成员，并生成 CP 小故事。
每个群每天一次，抽签记录持久化到本插件目录。
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent


cp_pairing = on_command(
    "cp",
    aliases={"CP", "群内配对", "CP抽签", "群内CP"},
    priority=5,
    block=True,
)

_HISTORY_FILE = Path(__file__).with_name("cp_history.json")

_STORIES = (
    "两人第一次见面是在雨天，一人借出伞，另一人负责把伞拿反。后来他们发现，方向虽然总是相反，但一起走就不会迷路。",
    "他们一个负责制造麻烦，一个负责收拾残局，群友一致认为这不是 CP，而是一套运行稳定的双人灾难处理系统。",
    "一个喜欢熬夜，一个负责提醒早睡；最后两人一起熬到了天亮，决定把‘明天一定早睡’作为共同的人生目标。",
    "他们在群里因为一件小事争论了半天，最后发现两个人都记错了。于是相视一笑，约定以后一起记错。",
    "一个像夏天一样热烈，一个像冬天一样冷静。奇妙的是，他们刚好把彼此的极端调成了舒服的温度。",
    "他们偶然在同一家店点了同样的东西，老板说这是缘分；两人认真讨论后决定，先从AA开始验证缘分。",
    "一个擅长讲冷笑话，一个擅长在笑话冷场时鼓掌。他们的默契，连空气都觉得很暖。",
    "命运把他们安排成今天的搭档。虽然两人都说只是随机，但谁也没有退出这场随机。",
    "他们的故事没有轰轰烈烈的开场，只有一句‘在吗’和一句‘在的’。可就是这两句话，后来变成了每天的固定节目。",
    "一个负责规划未来，一个负责临时改变计划。他们一路跌跌撞撞，却总能在同一个终点碰面。",
)


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_history() -> Dict[str, Any]:
    try:
        if not _HISTORY_FILE.exists():
            return {}
        data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_history(history: Dict[str, Any]) -> None:
    try:
        _HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 抽签本身不应因为记录文件不可写而失败。
        pass


def _member_name(member: Dict[str, Any]) -> str:
    return str(member.get("card") or member.get("nickname") or member.get("user_id"))


def _pick_members(
    members: List[Dict[str, Any]],
    self_id: int,
) -> Tuple[Dict[str, Any], Dict[str, Any]] | None:
    candidates = [
        member
        for member in members
        if int(member.get("user_id", 0)) != int(self_id)
        and not bool(member.get("unfriendly", False))
    ]
    if len(candidates) < 2:
        return None
    return tuple(random.sample(candidates, 2))  # type: ignore[return-value]


@cp_pairing.handle()
async def handle_cp(bot: Bot, event: MessageEvent) -> None:
    group_id_raw = getattr(event, "group_id", None)
    if group_id_raw is None:
        await bot.send_private_msg(
            user_id=event.user_id,
            message="CP 抽签是群内玩法，请在群聊中发送 /cp。",
        )
        return
    group_id = int(group_id_raw)
    today = _today()
    history = _load_history()
    old = history.get(str(group_id))

    if isinstance(old, dict) and old.get("date") == today:
        first = old.get("first_name", "第一位群友")
        second = old.get("second_name", "第二位群友")
        await bot.send_group_msg(
            group_id=group_id,
            message=f"本群今天已经 CP 抽签过啦：{first} × {second}\n明天再来抽新的配对吧！",
        )
        return

    try:
        response = await bot.call_api("get_group_member_list", group_id=group_id)
        members = response if isinstance(response, list) else []
    except Exception:
        await bot.send_group_msg(
            group_id=group_id,
            message="暂时无法获取群成员列表，CP 抽签失败，请确认 Bot 仍在群内。",
        )
        return

    pair = _pick_members(members, int(event.self_id))
    if pair is None:
        await bot.send_group_msg(group_id=group_id, message="群内可配对成员不足两人，暂时无法抽签。")
        return

    first, second = pair
    first_name = _member_name(first)
    second_name = _member_name(second)
    story = random.choice(_STORIES)
    history[str(group_id)] = {
        "date": today,
        "first_id": int(first.get("user_id", 0)),
        "second_id": int(second.get("user_id", 0)),
        "first_name": first_name,
        "second_name": second_name,
    }
    _save_history(history)

    await bot.send_group_msg(
        group_id=group_id,
        message=(
            f"【今日 CP 抽签】\n"
            f"{first_name}  ×  {second_name}\n\n"
            f"{story}\n\n"
            "今日配对已锁定，明天再来抽新的！"
        ),
    )
