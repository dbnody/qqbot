"""每日一言。"""

from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from app.quotes import daily_quote


quote_command = on_command("一言", aliases={"今日一句", "quote", "hitokoto"}, priority=10, block=True)


@quote_command.handle()
async def handle_quote(event: MessageEvent) -> None:
    if isinstance(event, GroupMessageEvent):
        scope = f"group:{event.group_id}"
    else:
        scope = f"private:{event.user_id}"
    await quote_command.finish(f"今日一句：\n“{daily_quote(scope)}”")
