"""戳一戳互动。

当有人戳中机器人时，随机发送一句回应或使用 OneBot 的 ``send_poke``
接口反戳对方。群聊和私聊均支持。
"""

from __future__ import annotations

import random

from nonebot import on_notice
from nonebot.adapters.onebot.v11 import Bot, PokeNotifyEvent


# 使用独立的 notice matcher，不拦截其它通知事件。
poke_reaction = on_notice(priority=5, block=False)

_TEXT_REPLIES = (
    "喵？谁在戳我！",
    "再戳就要反击了喵。",
    "检测到一只调皮的群友。",
    "别戳啦，认真说话喵。",
    "戳戳收到，给你一记可爱的回礼！",
    "喵呜——被你发现啦！",
    "轻一点喵，我可是会害羞的。",
    "你戳一下，我记你一次喵。",
    "警告：检测到可疑戳戳行为！",
    "今天也要和 Bot 好好相处喵。",
    "收到你的戳戳，心情增加一点点。",
    "再戳一下试试？我可要反戳啦！",
    "这是在召唤我吗，喵？",
    "戳戳能量已收集完毕！",
    "摸鱼被抓到了，先回你一个戳。",
    "喵喵喵？有事请直接说喵。",
    "你的戳戳申请已通过。",
    "别闹啦，给你一个友好的猫爪印。",
)


@poke_reaction.handle()
async def handle_poke(bot: Bot, event: PokeNotifyEvent) -> None:
    """仅处理目标为本 Bot 的戳一戳事件。"""

    # on_notice 会收到所有 notice，先过滤掉撤回、入群等其它通知。
    if not isinstance(event, PokeNotifyEvent):
        return

    # OneBot V11 的 PokeNotifyEvent 中 target_id 是被戳者 QQ。
    if event.target_id != event.self_id:
        return

    # 避免机器人自己触发自己时产生循环互动。
    if event.user_id == event.self_id:
        return

    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        if random.choice((True, False)):
            # NapCat/OneBot V11 支持 send_poke 动作时反戳；失败时发送文字兜底。
            try:
                await bot.call_api(
                    "send_poke",
                    group_id=group_id,
                    user_id=event.user_id,
                )
                return
            except Exception:
                pass

        await bot.send_group_msg(
            group_id=group_id,
            message=random.choice(_TEXT_REPLIES),
        )
        return

    # 私聊事件没有 group_id，使用私聊对应接口。
    if random.choice((True, False)):
        try:
            await bot.call_api("send_poke", user_id=event.user_id)
            return
        except Exception:
            pass

    await bot.send_private_msg(
        user_id=event.user_id,
        message=random.choice(_TEXT_REPLIES),
    )
