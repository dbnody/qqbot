"""DeepSeek 聊天主体：人格 + 记忆 + 表情 + 语音。

固定命令由更高优先级的插件处理；本插件只接住没被匹配的普通文本。
私聊直接对话，群聊需要 @Bot（或回复 Bot 的消息）。
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path

import httpx
from nonebot import get_driver, logger, on_command, on_message
from nonebot.adapters.onebot.v11 import (
    GroupMessageEvent,
    Message,
    MessageEvent,
    MessageSegment,
    PrivateMessageEvent,
)

from app import stickers
from app.ai_client import chat_reply, chat_reply_stream, is_configured, parse_reply
from app.memory import append_ai_memory, clear_ai_memory, consolidate, load_ai_memory
from app.persona import build_system_prompt, get_persona
from app.sticker_fetch import ensure_pack
from app.tts import synthesize, warmup
from app.voice_mode import is_voice_mode, set_voice_mode


@get_driver().on_startup
async def _warm_tts() -> None:
    """后台预热语音引擎，首条语音少等一秒。"""
    asyncio.create_task(warmup())


ai_chat = on_message(priority=99, block=False)
_semaphore = asyncio.Semaphore(3)
_last_request: dict[str, float] = {}


def _memory_scope(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group:{event.group_id}"
    return f"private:{event.user_id}"


def _configured_admin_ids() -> set[str]:
    """读取 Bot 管理员账号，用于群聊中的记忆管理权限。"""
    ids = {
        item.strip()
        for item in os.getenv("QQBOT_ADMIN_IDS", "").replace("，", ",").split(",")
        if item.strip().isdigit()
    }
    try:
        superusers = getattr(get_driver().config, "superusers", set())
        ids.update(str(item).strip() for item in superusers if str(item).strip().isdigit())
    except Exception:
        pass
    return ids


def _can_clear_memory(event: MessageEvent) -> bool:
    if not isinstance(event, GroupMessageEvent):
        return True
    return str(event.user_id) in _configured_admin_ids()


clear_memory_command = on_command("清除记忆", aliases={"清空记忆", "忘记本群"}, priority=10, block=True)


@clear_memory_command.handle()
async def handle_clear_memory(event: MessageEvent) -> None:
    if not _can_clear_memory(event):
        await clear_memory_command.finish("群聊中只有 Bot 管理员可以清除本群的 AI 记忆。")
    clear_ai_memory(_memory_scope(event))
    if isinstance(event, GroupMessageEvent):
        await clear_memory_command.finish("已清除本群的 AI 记忆（含摘要与事实），不会影响其他群。")
    await clear_memory_command.finish("已清除你的私聊 AI 记忆（含摘要与事实）。")


def _is_at_bot(event: MessageEvent) -> bool:
    self_id = str(event.self_id).strip()
    if bool(getattr(event, "to_me", False)):
        return True
    for segment in event.get_message():
        if segment.type in {"at", "mention"}:
            target_id = str(segment.data.get("qq", segment.data.get("user_id", ""))).strip()
            if target_id == self_id:
                return True
    raw_message = str(event.get_message())
    return f"[at:qq={self_id}]" in raw_message or f"[CQ:at,qq={self_id}]" in raw_message


def _is_reply_to_bot(event: MessageEvent) -> bool:
    reply = getattr(event, "reply", None)
    sender = getattr(reply, "sender", None)
    return sender is not None and str(getattr(sender, "user_id", "")) == str(event.self_id)


def _clean_question(event: MessageEvent) -> str:
    plain_text = event.get_plaintext().strip()
    if plain_text:
        return plain_text
    parts = []
    for segment in event.get_message():
        if segment.type in {"at", "mention"} and str(
            segment.data.get("qq", segment.data.get("user_id", ""))
        ).strip() == str(event.self_id).strip():
            continue
        if segment.type == "text":
            parts.append(str(segment.data.get("text", "")))
    return re.sub(r"\[(?:at:qq=|CQ:at,qq=)\d+\]", "", "".join(parts)).strip()


def _file_uri(path: Path) -> str:
    return path.resolve().as_uri()


# 用户明确要语音时，不管模型有没有加 [语音] 标签，都必须发语音。
VOICE_REQUEST = re.compile(
    r"(用|发|来|整|说|讲|读|念)(一?段?|个|句)?语音|语音(说|回|答|讲|聊|给)|用声音"
    r"|说给我听|念给我听|读给我听|读一下|念一下|来一句|说句话"
)
# 模型开始解释「语音只是标记」这类废话时，重问一次。
VOICE_META = re.compile(r"发不了|说不了|不能发|没有真声|不是真声|文字加|只是文字|标记而已|假装")


def _wants_voice(text: str) -> bool:
    return bool(VOICE_REQUEST.search(text or ""))


# 语音聊天模式：说「语音聊」就一直用语音回，说到「打字 / 用文字」才切回来。
VOICE_MODE_ON = re.compile(r"语音聊|用语音|语音对话|语音陪伴|以后都用语音|一直用语音")
VOICE_MODE_OFF = re.compile(r"打字|用文字|文字聊|别用语音|不要语音|别发语音|关掉语音|语音关")


def _update_voice_mode(scope: str, question: str) -> bool:
    """按这句话更新语音模式，返回更新后是否为语音模式。"""
    mode = is_voice_mode(scope)
    if VOICE_MODE_OFF.search(question):
        mode = False
    elif VOICE_MODE_ON.search(question):
        mode = True
    else:
        return mode
    set_voice_mode(scope, mode)
    logger.info(f"[AI] 语音模式 {'开启' if mode else '关闭'} scope={scope}")
    return mode


_SENTENCE_END = re.compile(r"[。！？!?…~～\n]")


async def _speak_stream(
    system_prompt: str, history: list[dict[str, str]], question: str, nickname: str, voice: str
) -> tuple[str, bool]:
    """边流式生成边合成：第一句合成好就发出去，不等整段说完。

    返回 (完整文本, 是否发出过语音)。
    """
    full = ""
    buffer = ""
    acc = ""
    pending: list[asyncio.Task] = []
    sent_any = False
    first = True
    aborted = False

    async def _queue(chunk: str) -> None:
        nonlocal aborted
        spoken = parse_reply(chunk).text.strip()
        if first and VOICE_META.search(spoken):
            aborted = True  # 模型在解释语音功能，别念出来，交给普通请求重试
            return
        if len(spoken) >= 2:
            pending.append(asyncio.create_task(synthesize(spoken, voice)))

    async def _drain(block: bool) -> None:
        nonlocal sent_any
        while pending and (block or pending[0].done()):
            path = await pending.pop(0)
            if path is not None:
                await ai_chat.send(Message(MessageSegment.record(_file_uri(path))))
                sent_any = True

    async for piece in chat_reply_stream(system_prompt, history, question, nickname):
        full += piece
        buffer += piece
        while (match := _SENTENCE_END.search(buffer)) is not None:
            acc += buffer[: match.end()]
            buffer = buffer[match.end() :]
            if len(acc) >= (6 if first else 24):
                await _queue(acc)
                if aborted:
                    return "", False
                acc = ""
                first = False
        await _drain(block=False)

    if (acc + buffer).strip():
        await _queue(acc + buffer)
    if aborted:
        return "", False
    await _drain(block=True)
    return parse_reply(full).text, sent_any


def _system_prompt(scope: str, question: str) -> str:
    return build_system_prompt(scope, question)


async def _consolidate_quietly(scope: str) -> None:
    try:
        if await consolidate(scope):
            logger.info(f"[AI] 记忆已更新 scope={scope}")
    except Exception as exc:
        logger.warning(f"[AI] 记忆整理失败：{type(exc).__name__}")


@ai_chat.handle()
async def handle_ai_chat(event: MessageEvent) -> None:
    logger.info(f"[AI] 收到消息，user_id={event.user_id} self_id={event.self_id}")
    if not is_configured():
        logger.warning("[AI] DeepSeek 未配置，跳过 AI 回复")
        return
    if str(event.user_id) == str(event.self_id):
        return
    if isinstance(event, GroupMessageEvent):
        # AI_GROUP_TRIGGER=all 时群里每条消息都接，默认只接 @ 和回复。
        trigger = os.getenv("AI_GROUP_TRIGGER", "at").strip().lower()
        if trigger != "all" and not (_is_at_bot(event) or _is_reply_to_bot(event)):
            return
    elif not isinstance(event, PrivateMessageEvent):
        return

    question = _clean_question(event)
    if not question or question.startswith(("/", "！", "!")):
        return

    scope = _memory_scope(event)
    user_key = f"{getattr(event, 'group_id', 'private')}:{event.user_id}"
    now = time.monotonic()
    if now - _last_request.get(user_key, 0) < 3:
        logger.info("[AI] 请求过于频繁，跳过")
        return
    _last_request[user_key] = now

    sender = event.sender
    nickname = str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "用户")
    history = load_ai_memory(scope)
    system_prompt = _system_prompt(scope, question)

    voice_mode = _update_voice_mode(scope, question)
    want_voice = voice_mode or _wants_voice(question)

    reply = None
    streamed_text = ""
    sent_voice = False
    async with _semaphore:
        if want_voice:
            # 流式：第一句合成好就先发出去，别等整段。
            try:
                streamed_text, sent_voice = await _speak_stream(
                    system_prompt, history, question, nickname, get_persona(scope).voice
                )
            except Exception as exc:
                logger.warning(f"[AI] 流式语音失败：{type(exc).__name__}")

        if not streamed_text:
            try:
                reply = await chat_reply(system_prompt, history, question, nickname)
                if want_voice and reply is not None and VOICE_META.search(reply.text):
                    # 模型在解释「语音只是标记」，重问一次，只要那句话本身。
                    logger.info("[AI] 回复在解释语音，重试一次")
                    retry = await chat_reply(
                        system_prompt,
                        history,
                        question + "\n（直接用这句话本身回答，不要解释语音、标签或功能）",
                        nickname,
                    )
                    if retry is not None and retry.text and not VOICE_META.search(retry.text):
                        reply = retry
            except httpx.HTTPStatusError as exc:
                logger.error(f"[AI] DeepSeek HTTP 错误 status={exc.response.status_code}")
            except Exception as exc:
                logger.error(f"[AI] DeepSeek 请求失败 type={type(exc).__name__}")

    if sent_voice and streamed_text:
        append_ai_memory(scope, "user", f"{nickname}：{question}")
        append_ai_memory(scope, "assistant", streamed_text)
        asyncio.create_task(_consolidate_quietly(scope))
        await ai_chat.finish()

    if reply is None:
        reply = parse_reply(streamed_text)
    if reply is None or not reply.text:
        await ai_chat.finish("……大肥鱼走神了，等会儿再问一次吧。")

    append_ai_memory(scope, "user", f"{nickname}：{question}")
    append_ai_memory(scope, "assistant", reply.text)
    asyncio.create_task(_consolidate_quietly(scope))

    if reply.voice or want_voice:
        # 要语音就只发语音：先发音频，成功后再 finish；失败才退回文字。
        audio = await synthesize(reply.text, get_persona(scope).voice)
        if audio is not None:
            try:
                await ai_chat.send(Message(MessageSegment.record(_file_uri(audio))))
            except Exception as exc:
                logger.warning(f"[AI] 发送语音失败：{type(exc).__name__}")
            else:
                await ai_chat.finish()

    message = Message(MessageSegment.text(reply.text))
    sticker = stickers.pick(reply.emotion) if reply.emotion else None
    if sticker is None and reply.emotion:
        # 一张图都没有，这次就地找几张。
        sticker = await ensure_pack(reply.emotion)
    elif reply.emotion and not stickers.fetched(reply.emotion):
        # 有图但还没大肥鱼的，后台补一批，下一句就用上。
        asyncio.create_task(ensure_pack(reply.emotion))
    if sticker is not None:
        message += MessageSegment.image(_file_uri(sticker))
    elif reply.emotion and (face_id := stickers.face(reply.emotion)) is not None:
        message += MessageSegment.face(int(face_id))

    await ai_chat.finish(message)
