"""今日运势。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from app.fortune import daily_fortune


fortune_command = on_command("今日运势", aliases={"运势", "fortune"}, priority=10, block=True)


@fortune_command.handle()
async def handle_fortune(event: MessageEvent) -> None:
    sender = event.sender
    nickname = str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "朋友")
    user_id = event.get_user_id()
    if isinstance(event, GroupMessageEvent):
        user_id = f"group:{event.group_id}:{user_id}"
    result = daily_fortune(user_id, nickname)
    await fortune_command.finish(
        f"{nickname} 的今日运势（{result['date']}）\n"
        f"综合运势：{result['level']}（{result['score']}分）\n"
        f"幸运颜色：{result['lucky_color']}\n"
        f"幸运数字：{result['lucky_number']}\n"
        f"建议：{result['advice']}\n\n"
        "仅供娱乐与自我激励。"
    )
