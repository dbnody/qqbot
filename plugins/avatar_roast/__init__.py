"""头像锐评：只在用户明确触发时分析指定 QQ 头像。"""

from __future__ import annotations

from pathlib import Path

import httpx
from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageEvent
from nonebot.exception import FinishedException
from nonebot.params import CommandArg

from app.ai_client import ask_ai, is_configured
from app.avatar import AvatarError, download_avatar, download_image


avatar_command = on_command("锐评头像", aliases={"头像锐评"}, priority=10, block=True)
# 兼容头像处理函数中保留的旧命令对象名称；不会创建第二个 Matcher。
roast_command = avatar_command


def _target_id(event: MessageEvent) -> str | None:
    for segment in event.get_message():
        if segment.type == "at":
            qq = str(segment.data.get("qq", "")).strip()
            if qq.isdigit() and qq != "all":
                return qq
    return event.get_user_id() if not isinstance(event, GroupMessageEvent) else None


def _message_id(receipt: object) -> int | None:
    value = receipt.get("message_id") if isinstance(receipt, dict) else getattr(receipt, "message_id", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@avatar_command.handle()
async def handle_avatar_roast(bot: Bot, event: MessageEvent, args=CommandArg()) -> None:
    if not is_configured():
        await avatar_command.finish("AI 接口尚未配置，暂时不能进行头像锐评。")
    target_id = _target_id(event)
    if target_id is None:
        await avatar_command.finish("用法：/锐评头像 @成员；私聊中可直接使用 /锐评头像 锐评自己的头像。")
    if str(target_id) == str(event.self_id):
        await avatar_command.finish("不评价我自己的头像啦，换一位成员试试喵。")

    target_name = target_id
    if isinstance(event, GroupMessageEvent):
        try:
            info = await bot.get_group_member_info(group_id=event.group_id, user_id=int(target_id))
            target_name = str(info.get("card") or info.get("nickname") or target_id)
        except Exception:
            pass

    notice_id: int | None = None
    image_path: Path | None = None
    try:
        try:
            notice_id = _message_id(await roast_command.send("正在读取头像并进行锐评，请稍候……"))
        except Exception:
            notice_id = None
        image_path = await download_avatar(target_id)
        answer = await ask_ai(
            "请对这张头像做一段友善、幽默、克制的审美锐评。只评价构图、色彩、光线、风格和整体氛围，避免攻击本人，不推断任何敏感个人属性。控制在 120 字以内。",
            target_name,
            image_path=str(image_path),
        )
        if notice_id is not None:
            try:
                await bot.call_api("delete_msg", message_id=notice_id)
            except Exception:
                logger.warning(f"[头像锐评] 撤回处理中提示失败 message_id={notice_id}")
        await roast_command.finish(f"{target_name} 的头像锐评：\n{answer}")
    except httpx.HTTPStatusError as exc:
        if notice_id is not None:
            try:
                await bot.call_api("delete_msg", message_id=notice_id)
            except Exception:
                pass
        if exc.response.status_code in {400, 404, 415}:
            await roast_command.finish("当前 AI 模型或接口不支持图片理解，请更换支持视觉的模型。")
        await roast_command.finish("图片 AI 服务暂时不可用，请稍后再试。")
    except (AvatarError, httpx.HTTPError, RuntimeError) as exc:
        if notice_id is not None:
            try:
                await bot.call_api("delete_msg", message_id=notice_id)
            except Exception:
                pass
        logger.warning(f"[头像锐评] 处理失败：{type(exc).__name__}")
        await avatar_command.finish(f"头像锐评失败：{exc}")
    except FinishedException:
        # Matcher.finish() 的正常结束信号，不能被通用异常处理当成失败。
        raise
    except Exception as exc:
        logger.warning(f"[头像锐评] 未知异常：{type(exc).__name__}")
        await roast_command.finish("头像锐评失败，请稍后再试。")
    finally:
        if image_path is not None:
            try:
                image_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(f"[头像锐评] 临时头像清理失败：{image_path}")
