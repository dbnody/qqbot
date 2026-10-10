"""轻量级修仙系统：查看、修炼和突破。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.params import CommandArg

from app.services import breakthrough, cultivate, cultivation_profile


cultivation_command = on_command("修仙", aliases={"修炼"}, priority=10, block=True)


def _nickname(event: MessageEvent) -> str:
    sender = event.sender
    return str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "修士")


def _scope_user_id(event: MessageEvent) -> str:
    user_id = event.get_user_id()
    return f"group:{event.group_id}:{user_id}" if isinstance(event, GroupMessageEvent) else user_id


@cultivation_command.handle()
async def handle_cultivation(event: MessageEvent, args=CommandArg()) -> None:
    action = args.extract_plain_text().strip().lower()
    user_id = _scope_user_id(event)
    nickname = _nickname(event)

    if action in {"修炼", "闭关", "练功", "cultivate"}:
        result = cultivate(user_id, nickname)
        await cultivation_command.finish(
            f"你修炼了一轮，获得 {result['gain']} 点修为。\n"
            f"当前境界：{result['realm']}，修为：{result['experience']}/{result['threshold'] or '圆满'}，"
            f"灵石：{result['spirit_stones']}"
        )

    if action in {"突破", "breakthrough"}:
        result = breakthrough(user_id, nickname)
        if result.get("max_realm"):
            await cultivation_command.finish("你已达到渡劫期，暂时没有更高境界。")
        if not result["success"]:
            await cultivation_command.finish(
                f"突破失败，还需要修炼至 {result['threshold']} 点修为。"
                f"当前：{result['experience']}/{result['threshold']}。"
            )
        await cultivation_command.finish(
            f"突破成功！恭喜从 {result['old_realm']} 晋升为 {result['realm']}！"
        )

    result = cultivation_profile(user_id, nickname)
    await cultivation_command.finish(
        f"修士：{nickname}\n"
        f"境界：{result['realm']}\n"
        f"修为：{result['experience']}/{result['threshold'] or '圆满'}\n"
        f"灵石：{result['spirit_stones']}\n\n"
        "用法：/修仙 修炼 或 /修仙 突破"
    )
