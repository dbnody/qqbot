"""文字和图片锐评，支持私聊与群聊。"""

from __future__ import annotations

from pathlib import Path

import httpx
from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg

from app.ai_client import ask_ai, is_configured
from app.avatar import AvatarError, download_avatar, download_image


roast_command = on_command("锐评", aliases={"评价", "吐槽"}, priority=10, block=True)
ROAST_PROMPT = (
    "请进行一段语言尖刀式、机智幽默、略带毒舌但有分寸的锐评。"
    "重点评价内容本身或图片中的构图、色彩、光线、风格和氛围，避免恶意攻击真实个人。"
    "不要推断年龄、健康、种族、身份、性取向、政治立场等敏感属性，不要编造看不到的信息。"
    "控制在 120 字以内，像一个有幽默感的朋友吐槽，最后可以给一句简短建议。"
)


def _target_id(event: MessageEvent) -> str | None:
    for segment in event.get_message():
        if segment.type == "at":
            qq = str(segment.data.get("qq", "")).strip()
            if qq.isdigit() and qq != "all":
                return qq
    return None


def _image_source(event: MessageEvent) -> str | None:
    for segment in event.get_message():
        if segment.type == "image":
            source = segment.data.get("url") or segment.data.get("file")
            if source:
                return str(source)
    return None


def _message_id(receipt: object) -> int | None:
    value = receipt.get("message_id") if isinstance(receipt, dict) else getattr(receipt, "message_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _delete_notice(bot: Bot, message_id: int | None) -> None:
    if message_id is None:
        return
    try:
        await bot.call_api("delete_msg", message_id=message_id)
    except Exception:
        logger.warning(f"[锐评] 撤回处理中提示失败 message_id={message_id}")


async def _target_name(bot: Bot, event: MessageEvent, target_id: str | None) -> str:
    if target_id and isinstance(event, GroupMessageEvent):
        try:
            info = await bot.get_group_member_info(group_id=event.group_id, user_id=int(target_id))
            return str(info.get("card") or info.get("nickname") or target_id)
        except Exception:
            pass
    return target_id or "这件事"


@roast_command.handle()
async def handle_roast(bot: Bot, event: MessageEvent, args=CommandArg()) -> None:
    if not is_configured():
        await roast_command.finish("AI 接口尚未配置，暂时不能进行锐评。")

    text = args.extract_plain_text().strip()
    target_id = _target_id(event)
    source = _image_source(event)
    image_path: Path | None = None
    remove_image = False
    notice_id: int | None = None
    try:
        if source:
            image_path, remove_image = await download_image(source)
        elif target_id:
            image_path = await download_avatar(target_id)
            remove_image = True
        if not text and not image_path:
            await roast_command.finish("用法：/锐评 内容、/锐评 图片，或在群里使用 /锐评 @成员 锐评其头像。")

        display_name = await _target_name(bot, event, target_id)
        question = text or "请锐评这张图片。"
        try:
            notice_id = _message_id(await roast_command.send("正在准备锐评，请稍候……"))
        except Exception:
            notice_id = None
        answer = await ask_ai(
            ROAST_PROMPT + "\n待锐评内容：" + question,
            display_name,
            image_path=str(image_path) if image_path else None,
        )
        await _delete_notice(bot, notice_id)
        await roast_command.finish(f"{display_name} 的锐评：\n{answer}")
    except httpx.HTTPStatusError as exc:
        await _delete_notice(bot, notice_id)
        if exc.response.status_code in {400, 404, 415} and image_path is not None:
            await roast_command.finish("当前 AI 模型或接口不支持图片理解，请更换支持视觉的模型。")
        await roast_command.finish("锐评 AI 服务暂时不可用，请稍后再试。")
    except (AvatarError, httpx.HTTPError, RuntimeError) as exc:
        await _delete_notice(bot, notice_id)
        logger.warning(f"[锐评] 处理失败：{type(exc).__name__}: {exc}")
        if isinstance(exc, RuntimeError):
            await roast_command.finish("锐评 AI 返回异常，请稍后重试；如果持续出现，请检查模型和接口配置。")
        await roast_command.finish(f"锐评失败：{exc}")
    except FinishedException:
        raise
    except Exception as exc:
        await _delete_notice(bot, notice_id)
        logger.warning(f"[锐评] 未知异常：{type(exc).__name__}")
        await roast_command.finish("锐评失败，请稍后再试。")
    finally:
        if remove_image and image_path is not None:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(f"[锐评] 临时图片清理失败：{image_path}")
