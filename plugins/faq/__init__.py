"""基础问答和简短自我介绍。"""

import re

from nonebot import on_message, on_regex
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.rule import Rule


MODEL_ANSWER = (
    "呐，我是小肥，由我的主人创造，现在正以小机器人的身份陪在你身边喵。\n"
    "如果你有什么想知道的，或者需要帮忙的事情，随时告诉我哦！"
)


def _mentioned_bot(event: MessageEvent) -> bool:
    if bool(getattr(event, "to_me", False)):
        return True
    self_id = str(event.self_id).strip()
    for segment in event.get_message():
        if segment.type in {"at", "mention"}:
            target_id = str(segment.data.get("qq", segment.data.get("user_id", ""))).strip()
            if target_id == self_id:
                return True
    raw = str(event.get_message())
    return f"[at:qq={self_id}]" in raw or f"[CQ:at,qq={self_id}]" in raw


async def _model_question_rule(event: MessageEvent) -> bool:
    text = event.get_plaintext().strip()
    if not re.search(r"你是(?:什么|哪种)模型", text):
        return False
    return not isinstance(event, GroupMessageEvent) or _mentioned_bot(event)


model_question = on_message(rule=Rule(_model_question_rule), priority=20, block=True)


@model_question.handle()
async def handle_model_question(event: MessageEvent) -> None:
    await model_question.finish(MODEL_ANSWER)


self_intro = on_regex(r"^(?:你是谁|你叫什么|介绍一下自己)[？?！!。.]?$", priority=20, block=True)


@self_intro.handle()
async def handle_self_intro() -> None:
    await self_intro.finish("我是小肥，一个QQ Bot，可以陪你聊天和玩小游戏。")


greeting = on_regex(r"^(?:你好|您好|嗨|hi|hello)[！!。,. ]*$", priority=20, block=True)


@greeting.handle()
async def handle_greeting() -> None:
    await greeting.finish("你好！发送 /help 可以查看我现在支持的功能。")


capabilities = on_regex(r"^(?:你能做什么|你会什么|有什么功能)[？?！!。.]?$", priority=20, block=True)


@capabilities.handle()
async def handle_capabilities() -> None:
    await capabilities.finish("我可以进行天气的查询和一些简单的小游戏。发送 /help 查看用法。")


thanks = on_regex(r"^(?:谢谢|感谢|多谢)[！!。.]?$", priority=20, block=True)


@thanks.handle()
async def handle_thanks() -> None:
    await thanks.finish("不客气，随时可以叫我。")
