"""自动识别群内 B 站链接并发送视频。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from nonebot import logger, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment

from app.bilibili import BilibiliError, download_video, fetch_video


bilibili_handler = on_message(priority=8, block=False)
_processing_groups: set[str] = set()


def _message_id(receipt: object) -> int | None:
    if isinstance(receipt, dict):
        value = receipt.get("message_id")
    else:
        value = getattr(receipt, "message_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _has_bilibili_link(text: str) -> bool:
    return bool(
        re.search(r"(?:https?://)?(?:www\.)?bilibili\.com/video/\S+", text, re.I)
        or re.search(r"https?://b23\.tv/[A-Za-z0-9]+", text, re.I)
        or re.search(r"\b(?:BV[0-9A-Za-z]{10}|av\d+)\b", text, re.I)
    )


def _message_content(event: GroupMessageEvent) -> str:
    """提取普通文本以及 QQ 分享卡片中的 URL。

    NapCat 对直接分享的 B 站内容可能发送为 share、json 或 xml 消息段，
    这类消息的链接不一定会出现在 event.get_plaintext() 中。
    """
    values: list[str] = [event.get_plaintext()]

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                collect(child)
        elif isinstance(value, str):
            decoded = value.replace("\\/", "/")
            for _ in range(2):
                decoded = unquote(decoded)
            values.append(decoded)

    for segment in event.get_message():
        if segment.type in {"share", "json", "xml", "text"}:
            collect(dict(segment.data))
    return "\n".join(value for value in values if value)


@bilibili_handler.handle()
async def handle_bilibili(bot: Bot, event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    text = _message_content(event).strip()
    if not text or not _has_bilibili_link(text):
        return
    group_key = str(event.group_id)
    if group_key in _processing_groups:
        return
    _processing_groups.add(group_key)
    notice_id: int | None = None
    downloaded_path: Path | None = None
    try:
        try:
            notice_id = _message_id(await bilibili_handler.send("正在解析 B 站视频，请稍候……"))
        except Exception:
            notice_id = None
        video = await fetch_video(text)
        if video is None:
            raise BilibiliError("无法识别该 B 站视频链接")
        downloaded_path = await download_video(video)
        if notice_id is not None:
            try:
                await bot.call_api("delete_msg", message_id=notice_id)
            except Exception:
                logger.warning(f"[B站] 撤回处理中提示失败 message_id={notice_id}")
        message = Message(
            [
                MessageSegment.text(f"B站视频：{video.title}\n"),
                MessageSegment.video(file=str(downloaded_path.resolve())),
            ]
        )
        await bilibili_handler.send(message)
    except BilibiliError as exc:
        if notice_id is not None:
            try:
                await bot.call_api("delete_msg", message_id=notice_id)
            except Exception:
                pass
        await bilibili_handler.send(f"B站视频处理失败：{exc}")
    except Exception as exc:
        logger.warning(f"[B站] 处理异常：{type(exc).__name__}")
        await bilibili_handler.send("B站视频处理失败，请稍后再试。")
    finally:
        # OneBot 的发送 API 返回后，临时视频已经上传完成，及时清理避免长期占满磁盘。
        if downloaded_path is not None:
            try:
                downloaded_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(f"[B站] 临时视频清理失败：{downloaded_path}")
        _processing_groups.discard(group_key)
