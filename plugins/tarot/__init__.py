"""塔罗牌抽取与 PNG 图片渲染。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from nonebot.params import CommandArg

from app.fortune import draw_tarot_card, render_tarot_card


tarot_command = on_command("塔罗", aliases={"塔罗牌", "tarot"}, priority=10, block=True)


@tarot_command.handle()
async def handle_tarot(event: MessageEvent, args=CommandArg()) -> None:
    question = args.extract_plain_text().strip() or "没有特别指定的问题"
    card, reversed_card = draw_tarot_card()
    image_path = render_tarot_card(card, reversed_card, event.get_user_id())
    position = "逆位" if reversed_card else "正位"
    meaning = card.reversed if reversed_card else card.upright
    text = (
        f"你的问题：{question}\n"
        f"抽到：{card.number} · {card.name}（{position}）\n"
        f"关键词：{card.keyword}\n"
        f"解读：{meaning}\n"
        "以下内容仅供娱乐与自我反思。"
    )
    try:
        await tarot_command.finish(
            Message([MessageSegment.text(text), MessageSegment.image(file=str(image_path.resolve()))])
        )
    finally:
        image_path.unlink(missing_ok=True)
