"""AI 兜底聊天。

固定命令和 FAQ 由更高优先级的插件处理；本插件只处理未被匹配的普通文本。
私聊可以直接提问，群聊需要 @Bot，避免对群内所有消息自动回复。
"""

from __future__ import annotations

import asyncio
import re
import time

import httpx
from nonebot import logger, on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent, PrivateMessageEvent

from app.ai_client import ask_ai, is_configured
from app.memory import append_ai_memory, clear_ai_memory, load_ai_memory


ai_chat = on_message(priority=99, block=False)
_semaphore = asyncio.Semaphore(2)
_last_request: dict[str, float] = {}


def _memory_scope(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group:{event.group_id}"
    return f"private:{event.user_id}"


clear_memory_command = on_command("清除记忆", aliases={"清空记忆", "忘记本群"}, priority=10, block=True)


@clear_memory_command.handle()
async def handle_clear_memory(event: MessageEvent) -> None:
    clear_ai_memory(_memory_scope(event))
    if isinstance(event, GroupMessageEvent):
        await clear_memory_command.finish("已清除本群的 AI 记忆，不会影响其他群。")
    else:
        await clear_memory_command.finish("已清除你的私聊 AI 记忆，不会影响其他用户。")


def _is_at_bot(event: MessageEvent) -> bool:
    self_id = str(event.self_id).strip()
    # NoneBot/OneBot 在消息被 @Bot 时通常会直接标记 to_me。
    if bool(getattr(event, "to_me", False)):
        return True
    segments = list(event.get_message())
    logger.info(f"[AI] 消息段诊断：{[(segment.type, dict(segment.data)) for segment in segments]}")
    for segment in segments:
        if segment.type in {"at", "mention"}:
            target_id = str(segment.data.get("qq", segment.data.get("user_id", ""))).strip()
            if target_id == self_id:
                return True
    # NapCat 的日志格式为 [at:qq=123456]，兼容其字符串化消息格式。
    raw_message = str(event.get_message())
    if f"[at:qq={self_id}]" in raw_message or f"[CQ:at,qq={self_id}]" in raw_message:
        return True
    return False


def _clean_question(event: MessageEvent) -> str:
    # get_plaintext 会自动去掉 OneBot 的 at 段，优先使用它。
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


def _message_id(receipt: object) -> int | None:
    """从 OneBot send_msg 返回值中提取可撤回的 message_id。"""
    if isinstance(receipt, dict):
        value = receipt.get("message_id")
    else:
        value = getattr(receipt, "message_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@ai_chat.handle()
async def handle_ai_chat(bot: Bot, event: MessageEvent) -> None:
    logger.info(f"[AI] 收到消息，user_id={event.user_id} self_id={event.self_id}")
    if not is_configured():
        logger.warning("[AI] AI_API_KEY 未配置，跳过 AI 回复")
        return
    if str(event.user_id) == str(event.self_id):
        logger.info("[AI] 忽略 Bot 自己发送的消息")
        return
    if isinstance(event, GroupMessageEvent):
        if not _is_at_bot(event):
            logger.info("[AI] 群消息未 @Bot，跳过 AI 回复")
            return
    elif isinstance(event, PrivateMessageEvent):
        # 私聊是 Bot 与用户的一对一会话，不要求也不处理 @Bot 标记。
        logger.info("[AI] 私聊消息，直接进入 AI 回复流程")
    else:
        logger.info(f"[AI] 暂不处理消息类型：{type(event).__name__}")
        return

    question = _clean_question(event)
    if not question or question.startswith(("/", "！", "!")):
        logger.info("[AI] 消息不是可处理的普通问题，跳过")
        return

    user_key = f"{getattr(event, 'group_id', 'private')}:{event.user_id}"
    now = time.monotonic()
    if now - _last_request.get(user_key, 0) < 5:
        logger.info("[AI] 请求过于频繁，跳过")
        return
    _last_request[user_key] = now

    sender = event.sender
    nickname = str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "用户")
    memory_scope = _memory_scope(event)
    history = load_ai_memory(memory_scope)
    processing_message_id: int | None = None
    try:
        receipt = await ai_chat.send("正在处理你的问题，请稍候……")
        processing_message_id = _message_id(receipt)
        if processing_message_id is None:
            logger.warning("[AI] 正在处理提示未返回 message_id，无法自动撤回")
    except Exception as exc:
        # 提示消息发送失败不应阻断后续 AI 回复。
        logger.warning(f"[AI] 发送处理中提示失败：{type(exc).__name__}")
    ai_success = False
    async with _semaphore:
        try:
            answer = await ask_ai(question, nickname, history)
            ai_success = True
            logger.info(f"[AI] Kimi 请求成功，回答长度={len(answer)}")
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error(f"[AI] Kimi HTTP 错误 status={status}")
            if status in {401, 403}:
                answer = "AI 接口鉴权失败，请检查 API Key、接口地址和模型配置。"
            elif status == 429:
                answer = "AI 当前请求太频繁，请稍后再试。"
            else:
                answer = "AI 服务暂时不可用，请稍后再试。"
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.error(f"[AI] Kimi 请求失败 type={type(exc).__name__}")
            answer = "AI 服务暂时不可用，请检查网络或接口配置。"
    if ai_success and answer:
        try:
            append_ai_memory(memory_scope, "user", f"{nickname}：{question}")
            append_ai_memory(memory_scope, "assistant", answer)
        except Exception as exc:
            logger.warning(f"[AI] 保存会话记忆失败：{type(exc).__name__}")
    if processing_message_id is not None:
        try:
            await bot.call_api("delete_msg", message_id=processing_message_id)
            logger.info(f"[AI] 已撤回处理中提示 message_id={processing_message_id}")
        except Exception as exc:
            # NapCat 关闭撤回权限或消息过期时，仍然发送最终答案。
            logger.warning(f"[AI] 撤回处理中提示失败 message_id={processing_message_id}：{type(exc).__name__}")
    logger.info("[AI] 准备发送回复")
    await ai_chat.finish(answer)
