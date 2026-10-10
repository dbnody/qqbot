"""多人 21 点。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg

from app.games import blackjack_command


blackjack = on_command("21点", aliases={"21", "二十一点", "blackjack"}, priority=10, block=True)


def _room_id(event: MessageEvent) -> str:
    group_id = getattr(event, "group_id", None)
    return f"group:{group_id}" if group_id is not None else f"private:{event.get_user_id()}"


@blackjack.handle()
async def handle_blackjack(event: MessageEvent, args=CommandArg()) -> None:
    sender = event.sender
    nickname = str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "玩家")
    action = args.extract_plain_text().strip()
    await blackjack.finish(blackjack_command(_room_id(event), event.get_user_id(), nickname, action))
