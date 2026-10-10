"""群主/管理员专用群管理功能。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent
from nonebot.params import CommandArg

from app.group_admin import check_management_permission, parse_target_and_minutes, protected_target_error


management_help = on_command("群管", aliases={"群管理", "群管帮助"}, priority=10, block=True)


@management_help.handle()
async def handle_management_help(bot: Bot, event: GroupMessageEvent) -> None:
    error = await check_management_permission(bot, event)
    if error:
        await management_help.finish(error)
    await management_help.finish(
        "群管理命令：\n"
        "/ban @成员 分钟（1分钟-30天）\n"
        "/unban @成员\n"
        "/ta @成员\n"
        "/群管帮助"
    )


mute_command = on_command("ban", aliases={"禁言", "mute"}, priority=10, block=True)


@mute_command.handle()
async def handle_mute(bot: Bot, event: GroupMessageEvent, args=CommandArg()) -> None:
    error = await check_management_permission(bot, event)
    if error:
        await mute_command.finish(error)
    target_id, minutes = parse_target_and_minutes(event.get_message())
    if target_id is None:
        await mute_command.finish("用法：/ban @成员 分钟，例如：/ban @某人 10分钟")
    target_error = await protected_target_error(bot, event, target_id)
    if target_error:
        await mute_command.finish(target_error)
    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=target_id, duration=minutes * 60)
    except Exception:
        await mute_command.finish("禁言失败，请确认机器人权限和目标仍在群内。")
    await mute_command.finish(f"已将 {target_id} 禁言 {minutes} 分钟。")


unmute_command = on_command("unban", aliases={"解禁", "解除禁言", "unmute"}, priority=10, block=True)


@unmute_command.handle()
async def handle_unmute(bot: Bot, event: GroupMessageEvent, args=CommandArg()) -> None:
    error = await check_management_permission(bot, event)
    if error:
        await unmute_command.finish(error)
    target_id, _ = parse_target_and_minutes(event.get_message())
    if target_id is None:
        await unmute_command.finish("用法：/unban @成员")
    try:
        await bot.set_group_ban(group_id=event.group_id, user_id=target_id, duration=0)
    except Exception:
        await unmute_command.finish("解除禁言失败，请确认机器人权限和目标仍在群内。")
    await unmute_command.finish(f"已解除 {target_id} 的禁言。")


kick_command = on_command("ta", aliases={"踢人", "踢出", "kick"}, priority=10, block=True)


@kick_command.handle()
async def handle_kick(bot: Bot, event: GroupMessageEvent, args=CommandArg()) -> None:
    error = await check_management_permission(bot, event)
    if error:
        await kick_command.finish(error)
    target_id, _ = parse_target_and_minutes(event.get_message())
    if target_id is None:
        await kick_command.finish("用法：/ta @成员")
    target_error = await protected_target_error(bot, event, target_id)
    if target_error:
        await kick_command.finish(target_error)
    try:
        await bot.set_group_kick(group_id=event.group_id, user_id=target_id, reject_add_request=False)
    except Exception:
        await kick_command.finish("踢人失败，请确认机器人权限和目标仍在群内。")
    await kick_command.finish(f"已将 {target_id} 移出本群。")
