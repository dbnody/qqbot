"""每日签到功能。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent

from app.services import sign_in


sign_command = on_command("签到", aliases={"sign", "打卡"}, priority=10, block=True)


@sign_command.handle()
async def handle_sign(event: MessageEvent) -> None:
    sender = event.sender
    nickname = getattr(sender, "card", None) or getattr(sender, "nickname", None) or "QQ用户"
    user_id = event.get_user_id()
    if isinstance(event, GroupMessageEvent):
        user_id = f"group:{event.group_id}:{user_id}"
    result = sign_in(user_id, str(nickname))
    if not result["success"]:
        await sign_command.finish("今天已经签到过啦，明天再来吧。")
    await sign_command.finish(
        f"签到成功！获得 {result['reward']} 点灵气，累计签到 {result['total']} 天。"
    )
