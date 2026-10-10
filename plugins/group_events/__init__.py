"""群成员加入和退出提示。"""

from nonebot import on_notice
from nonebot.adapters.onebot.v11 import Bot, GroupDecreaseNoticeEvent, GroupIncreaseNoticeEvent


group_events = on_notice(priority=5, block=False)


@group_events.handle()
async def handle_group_events(
    bot: Bot, event: GroupIncreaseNoticeEvent | GroupDecreaseNoticeEvent
) -> None:
    if isinstance(event, GroupIncreaseNoticeEvent):
        await bot.send_group_msg(
            group_id=event.group_id,
            message=f"欢迎新成员 {event.user_id} 加入本群！发送 /help 可以查看 Bot 功能。",
        )
    elif isinstance(event, GroupDecreaseNoticeEvent):
        action = "被移出" if event.sub_type == "kick" else "离开"
        await bot.send_group_msg(
            group_id=event.group_id,
            message=f"成员 {event.user_id} 已{action}本群，祝一路顺风。",
        )
