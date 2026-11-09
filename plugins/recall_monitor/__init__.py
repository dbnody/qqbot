"""撤回消息监听与管理员转发。

撤回通知本身不携带原消息内容，因此先缓存收到的消息段；撤回时再优先
使用缓存，缓存缺失时尝试调用 OneBot get_msg。媒体不写入长期目录，转发
完成后释放缓存，避免占用磁盘。
"""

from __future__ import annotations

import os
from collections import OrderedDict
from pathlib import Path
from typing import Any

from nonebot import get_driver, logger, on_message, on_notice
from nonebot.adapters.onebot.v11 import (
    Bot,
    FriendRecallNoticeEvent,
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    Message,
    MessageEvent,
    MessageSegment,
)


# 在 .env 中通过 QQBOT_ADMIN_IDS 配置管理员，不在源码中写入个人 QQ 号。
DEFAULT_ADMIN_ID = ""
_message_cache: OrderedDict[int, dict[str, Any]] = OrderedDict()
_CACHE_LIMIT = 2000


def _admin_ids() -> set[str]:
    configured = os.getenv("QQBOT_ADMIN_IDS", "")
    ids = {item.strip() for item in configured.split(",") if item.strip().isdigit()}
    if DEFAULT_ADMIN_ID.isdigit():
        ids.add(DEFAULT_ADMIN_ID)
    try:
        superusers = getattr(get_driver().config, "superusers", set())
        ids.update(str(item) for item in superusers if str(item).isdigit())
    except Exception:
        pass
    return ids


def _copy_segments(message: Message) -> list[dict[str, Any]]:
    return [{"type": segment.type, "data": dict(segment.data)} for segment in message]


def _cache_message(event: MessageEvent) -> None:
    message_id = getattr(event, "message_id", None)
    if message_id is None:
        return
    _message_cache[int(message_id)] = {
        "segments": _copy_segments(event.get_message()),
        "user_id": str(event.user_id),
        "group_id": str(getattr(event, "group_id", "")),
    }
    _message_cache.move_to_end(int(message_id))
    while len(_message_cache) > _CACHE_LIMIT:
        _message_cache.popitem(last=False)


message_cache = on_message(priority=0, block=False)


@message_cache.handle()
async def handle_message_cache(event: MessageEvent) -> None:
    if str(event.user_id) == str(event.self_id):
        return
    _cache_message(event)


def _segment_message(segments: list[dict[str, Any]]) -> Message:
    result = Message()
    for item in segments:
        segment_type = str(item.get("type", "text"))
        data = dict(item.get("data") or {})
        # URL 比 file ID 更适合跨会话转发；OneBot 支持用 file 字段发送 URL。
        if segment_type in {"image", "video", "record", "file"} and data.get("url"):
            data["file"] = data["url"]
        try:
            result.append(MessageSegment(segment_type, data))
        except Exception:
            result.append(MessageSegment.text(f"[不支持的消息类型：{segment_type}]")
        )
    return result


async def _load_recalled(bot: Bot, message_id: int) -> dict[str, Any] | None:
    cached = _message_cache.get(message_id)
    if cached:
        return cached
    try:
        payload = await bot.get_msg(message_id=message_id)
        raw_message = payload.get("message")
        if raw_message is None:
            return None
        segments = raw_message if isinstance(raw_message, list) else [{"type": "text", "data": {"text": str(raw_message)}}]
        return {"segments": segments, "user_id": str(payload.get("user_id", "")), "group_id": str(payload.get("group_id", ""))}
    except Exception as exc:
        logger.warning(f"[撤回监听] 无法获取原消息 message_id={message_id}：{type(exc).__name__}")
        return None


async def _forward_recall(bot: Bot, event: GroupRecallNoticeEvent | FriendRecallNoticeEvent) -> None:
    # 不监听 Bot 自己发送的消息，或由 Bot 执行撤回操作的消息。
    if str(event.user_id) == str(event.self_id):
        return
    if isinstance(event, GroupRecallNoticeEvent) and str(event.operator_id) == str(event.self_id):
        return

    message_id = int(event.message_id)
    recalled = await _load_recalled(bot, message_id)
    if recalled is None:
        return
    if isinstance(event, GroupRecallNoticeEvent):
        source = f"群聊 {event.group_id}，发送者 QQ {event.user_id}，操作者 QQ {event.operator_id}"
    else:
        source = f"私聊，发送者 QQ {event.user_id}"
    forwarded = Message([MessageSegment.text(f"[撤回消息]\n来源：{source}\n消息 ID：{message_id}\n")])
    forwarded += _segment_message(recalled["segments"])
    success = 0
    for admin_id in _admin_ids():
        try:
            await bot.send_private_msg(user_id=int(admin_id), message=forwarded)
            success += 1
        except Exception as exc:
            logger.warning(f"[撤回监听] 转发管理员失败 admin_id={admin_id}：{type(exc).__name__}")
    if success == len(_admin_ids()):
        _message_cache.pop(message_id, None)
        logger.info(f"[撤回监听] 已转发并释放缓存 message_id={message_id}")


recall_notice = on_notice(priority=4, block=False)


@recall_notice.handle()
async def handle_recall_notice(
    bot: Bot, event: GroupRecallNoticeEvent | FriendRecallNoticeEvent
) -> None:
    if not isinstance(event, (GroupRecallNoticeEvent, FriendRecallNoticeEvent)):
        return
    await _forward_recall(bot, event)
