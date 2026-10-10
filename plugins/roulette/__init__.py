"""左轮轮盘赌。

规则：一把六发左轮只装一发子弹，玩家轮流扣动扳机。每次开局随机
选择起始弹巢，因此第一轮中弹概率为 1/6；未中后转到下一弹巢，最多
六次必定结束。群聊中的中弹者会被禁言 60 秒。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent
from nonebot.params import CommandArg


@dataclass
class RouletteGame:
    owner_id: int
    players: List[int] = field(default_factory=list)
    names: Dict[int, str] = field(default_factory=dict)
    bullet_slot: int = field(default_factory=lambda: random.randrange(6))
    chamber: int = 0
    started: bool = False
    solo: bool = False


_games: Dict[str, RouletteGame] = {}

roulette = on_command(
    "轮盘赌",
    aliases={"俄罗斯轮盘", "左轮赌"},
    priority=5,
    block=True,
)


def _game_key(event: MessageEvent) -> str:
    group_id = getattr(event, "group_id", None)
    return f"group:{group_id}" if group_id is not None else f"private:{event.user_id}"


def _display_name(event: MessageEvent) -> str:
    sender = getattr(event, "sender", None)
    return getattr(sender, "card", None) or getattr(sender, "nickname", None) or str(event.user_id)


def _help_text() -> str:
    return (
        "左轮轮盘赌用法：\n"
        "/轮盘赌 单人 —— 开始单人游戏\n"
        "/轮盘赌 多人 —— 创建多人房间\n"
        "/轮盘赌 加入 —— 加入当前房间\n"
        "/轮盘赌 开始 —— 房主开始游戏（至少两人）\n"
        "/轮盘赌 扣扳机 —— 当前玩家扣动扳机\n"
        "/轮盘赌 状态 —— 查看当前玩家和房间状态\n"
        "/轮盘赌 退出 —— 退出当前房间"
    )


async def _send(bot: Bot, event: MessageEvent, text: str) -> None:
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        await bot.send_group_msg(group_id=group_id, message=text)
    else:
        await bot.send_private_msg(user_id=event.user_id, message=text)


async def _ban_loser(bot: Bot, event: MessageEvent, user_id: int) -> bool:
    group_id = getattr(event, "group_id", None)
    if group_id is None:
        return False
    try:
        await bot.call_api(
            "set_group_ban",
            group_id=group_id,
            user_id=user_id,
            duration=60,
        )
        return True
    except Exception:
        return False


@roulette.handle()
async def handle_roulette(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> None:
    command = args.extract_plain_text().strip().lower()
    key = _game_key(event)
    game = _games.get(key)

    if not command or command in {"帮助", "help"}:
        await _send(bot, event, _help_text())
        return

    if command in {"单人", "自己玩", "solo"}:
        game = RouletteGame(
            owner_id=event.user_id,
            players=[event.user_id],
            names={event.user_id: _display_name(event)},
            started=True,
            solo=True,
        )
        _games[key] = game
        await _send(bot, event, "左轮已装填一发子弹。单人游戏开始，请发送 /轮盘赌 扣扳机。")
        return

    if command in {"多人", "多人玩", "多人游戏", "multi"}:
        if game and game.started:
            await _send(bot, event, "当前已经有一局进行中，请等待本局结束。")
            return
        _games[key] = RouletteGame(
            owner_id=event.user_id,
            players=[event.user_id],
            names={event.user_id: _display_name(event)},
        )
        await _send(bot, event, "多人房间已创建。发送 /轮盘赌 加入，房主发送 /轮盘赌 开始。")
        return

    if game is None:
        await _send(bot, event, "还没有轮盘赌房间，请先发送 /轮盘赌 单人 或 /轮盘赌 多人。")
        return

    if command in {"加入", "join"}:
        if game.started:
            await _send(bot, event, "本局已经开始，不能中途加入。")
        elif event.user_id in game.players:
            await _send(bot, event, "你已经在房间里了。")
        elif len(game.players) >= 6:
            await _send(bot, event, "左轮最多支持 6 名玩家。")
        else:
            game.players.append(event.user_id)
            game.names[event.user_id] = _display_name(event)
            await _send(bot, event, f"{_display_name(event)} 加入房间，当前人数：{len(game.players)}。")
        return

    if command in {"开始", "start"}:
        if game.started:
            await _send(bot, event, "本局已经开始了。")
        elif event.user_id != game.owner_id:
            await _send(bot, event, "只有房主可以开始游戏。")
        elif len(game.players) < 2:
            await _send(bot, event, "多人游戏至少需要 2 名玩家。")
        else:
            game.started = True
            first = game.names[game.players[0]]
            await _send(bot, event, f"左轮已装填一发子弹，轮流扣扳机。现在轮到 {first}。")
        return

    if command in {"状态", "信息", "status"}:
        names = "、".join(game.names[player] for player in game.players)
        if game.started:
            current = game.names[game.players[game.chamber % len(game.players)]]
            text = f"当前玩家：{current}\n玩家列表：{names}\n已扣扳机：{game.chamber} 次"
        else:
            text = f"等待开始，玩家列表：{names}"
        await _send(bot, event, text)
        return

    if command in {"退出", "结束", "quit"}:
        if event.user_id == game.owner_id or event.user_id not in game.players:
            _games.pop(key, None)
            await _send(bot, event, "本局轮盘赌已结束。")
        else:
            game.players.remove(event.user_id)
            game.names.pop(event.user_id, None)
            await _send(bot, event, "你已退出当前房间。")
        return

    if command not in {"扣扳机", "开枪", "开火", "trigger", "go"}:
        await _send(bot, event, _help_text())
        return

    if not game.started:
        await _send(bot, event, "多人房间还未开始，请先加入后由房主发送 /轮盘赌 开始。")
        return

    current_user = game.players[game.chamber % len(game.players)]
    if event.user_id != current_user:
        await _send(bot, event, f"还没轮到你，请等待 {game.names[current_user]}。")
        return

    current_name = game.names[current_user]
    if game.chamber == game.bullet_slot:
        muted = await _ban_loser(bot, event, current_user)
        _games.pop(key, None)
        punishment = "已禁言 60 秒" if muted else "当前为私聊或 Bot 没有群管理权限，未能执行禁言"
        await _send(bot, event, f"砰！{current_name} 中弹了！本局结束，{punishment}。")
        return

    game.chamber += 1
    next_user = game.players[game.chamber % len(game.players)]
    await _send(
        bot,
        event,
        f"咔哒……{current_name} 幸存！下一位是 {game.names[next_user]}。",
    )
