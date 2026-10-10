"""群消息违禁词检测。"""

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent

from app.group_admin import forbidden_mute_seconds, is_bot_admin, is_operator_admin, matched_forbidden_word


moderation = on_message(priority=1, block=False)


@moderation.handle()
async def handle_moderation(bot: Bot, event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent) or is_operator_admin(event):
        return
    word = matched_forbidden_word(event.get_plaintext())
    if word is None or not await is_bot_admin(bot, event.group_id, event.self_id):
        return
    try:
        await bot.delete_msg(message_id=event.message_id)
        mute_seconds = forbidden_mute_seconds()
        if mute_seconds > 0:
            await bot.set_group_ban(group_id=event.group_id, user_id=event.user_id, duration=mute_seconds)
        await bot.send_group_msg(
            group_id=event.group_id,
            message=f"检测到违禁词，已删除相关消息并处理（关键词：{word}）。",
        )
    except Exception:
        return
