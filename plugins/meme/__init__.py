"""本地梗图生成器。

用法：/meme 模板 文字
例如：/meme 哭泣猫猫 今天也要努力上班
"""

from __future__ import annotations

import os
import random
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.params import CommandArg


meme = on_command(
    "meme",
    aliases={"梗图", "表情包", "做图"},
    priority=5,
    block=True,
)

meme_templates = on_command(
    "meme模板",
    aliases={"梗图模板", "模板列表"},
    priority=5,
    block=True,
)

_TEMPLATES = {
    "哭泣猫猫": "crying_cat",
    "哭猫": "crying_cat",
    "猫猫": "crying_cat",
    "完美": "perfect",
    "神图": "masterpiece",
    "pornhub": "pornhub",
    "pornhub标题图": "pornhub",
    "举牌小人": "sign",
    "举牌": "sign",
    "熊猫人": "panda",
    "狗头": "doge",
    "震惊": "shocked",
    "经典": "classic",
    "彩虹": "rainbow",
}

_TEMPLATE_HELP = "、".join(("哭泣猫猫", "完美", "神图", "PornHub标题图", "举牌小人", "熊猫人", "狗头", "震惊", "经典", "彩虹"))


def _load_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont

        return Image, ImageDraw, ImageFont
    except ImportError:
        return None


def _font(ImageFont, size: int):
    font_paths = (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, width: int = 16) -> str:
    text = " ".join(text.strip().split())
    return "\n".join(text[i : i + width] for i in range(0, len(text), width))


def _center(draw, canvas, text: str, font, fill=(255, 255, 255), y: int | None = None, stroke=0):
    box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=8, stroke_width=stroke)
    x = (canvas.width - (box[2] - box[0])) // 2
    top = y if y is not None else (canvas.height - (box[3] - box[1])) // 2
    draw.multiline_text((x, top), text, font=font, fill=fill, align="center", spacing=8, stroke_width=stroke, stroke_fill=(0, 0, 0))


def _draw_face(draw, cx: int, cy: int, radius: int, color=(245, 203, 157), shocked=False):
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline=(50, 35, 30), width=5)
    eye_y = cy - radius // 4
    if shocked:
        draw.ellipse((cx - radius // 3, eye_y - 12, cx - radius // 3 + 24, eye_y + 15), fill=(25, 25, 25))
        draw.ellipse((cx + radius // 3 - 24, eye_y - 12, cx + radius // 3, eye_y + 15), fill=(25, 25, 25))
        draw.ellipse((cx - 22, cy + radius // 5, cx + 22, cy + radius // 2), fill=(50, 20, 20))
    else:
        draw.ellipse((cx - radius // 3, eye_y, cx - radius // 3 + 18, eye_y + 18), fill=(35, 35, 35))
        draw.ellipse((cx + radius // 3 - 18, eye_y, cx + radius // 3, eye_y + 18), fill=(35, 35, 35))
        draw.arc((cx - radius // 3, cy, cx + radius // 3, cy + radius // 2), 15, 165, fill=(70, 30, 30), width=5)


def _render(template: str, text: str, Image, ImageDraw, ImageFont):
    width, height = 900, 650
    image = Image.new("RGB", (width, height), (35, 35, 45))
    draw = ImageDraw.Draw(image)
    title = _wrap_text(text, 15)
    big = _font(ImageFont, 52)
    medium = _font(ImageFont, 38)
    small = _font(ImageFont, 28)

    if template == "crying_cat":
        image.paste((185, 218, 238), (0, 0, width, height))
        draw.ellipse((230, 120, 670, 560), fill=(245, 202, 170), outline=(95, 65, 55), width=8)
        draw.polygon(((250, 190), (255, 50), (370, 145)), fill=(245, 202, 170), outline=(95, 65, 55))
        draw.polygon(((530, 145), (645, 50), (650, 190)), fill=(245, 202, 170), outline=(95, 65, 55))
        draw.ellipse((330, 260, 370, 300), fill=(35, 35, 35))
        draw.ellipse((530, 260, 570, 300), fill=(35, 35, 35))
        draw.line((350, 315, 300, 470), fill=(55, 160, 235), width=13)
        draw.line((550, 315, 600, 470), fill=(55, 160, 235), width=13)
        draw.arc((390, 330, 510, 450), 200, 340, fill=(75, 35, 35), width=8)
        _center(draw, image, title, medium, fill=(255, 255, 255), y=12, stroke=2)
    elif template == "perfect":
        image.paste((52, 158, 76), (0, 0, width, height))
        for x, y in ((90, 100), (790, 120), (135, 500), (760, 520)):
            draw.text((x, y), "★", font=big, fill=(255, 224, 75))
        draw.ellipse((260, 125, 640, 505), fill=(255, 223, 80), outline=(255, 245, 170), width=8)
        draw.arc((330, 225, 570, 430), 15, 165, fill=(55, 95, 30), width=18)
        draw.ellipse((350, 235, 380, 270), fill=(55, 95, 30))
        draw.ellipse((520, 235, 550, 270), fill=(55, 95, 30))
        _center(draw, image, title, medium, fill=(255, 255, 255), y=15, stroke=2)
    elif template == "masterpiece":
        image.paste((102, 30, 145), (0, 0, width, height))
        for i in range(8):
            draw.line((450, 300, 60 + i * 110, 40), fill=(255, 215, 75), width=5)
            draw.line((450, 300, 60 + i * 110, 610), fill=(255, 120, 180), width=5)
        _draw_face(draw, 450, 315, 150)
        draw.text((185, 500), "这不是普通的图", font=small, fill=(255, 235, 110))
        _center(draw, image, title, medium, fill=(255, 255, 255), y=20, stroke=2)
    elif template == "pornhub":
        image.paste((0, 0, 0), (0, 0, width, height))
        draw.rectangle((0, 225, width, 425), fill=(255, 145, 0))
        ph = _font(ImageFont, 86)
        _center(draw, image, "PornHub", ph, fill=(255, 255, 255), y=70, stroke=3)
        draw.rectangle((385, 225, 515, 425), fill=(255, 145, 0))
        _center(draw, image, title, medium, fill=(0, 0, 0), y=270, stroke=1)
    elif template == "sign":
        image.paste((155, 205, 235), (0, 0, width, height))
        draw.ellipse((385, 375, 515, 505), fill=(245, 203, 157), outline=(50, 40, 40), width=5)
        draw.line((450, 505, 450, 650), fill=(35, 35, 35), width=18)
        draw.line((450, 535, 315, 620), fill=(35, 35, 35), width=15)
        draw.line((450, 535, 585, 620), fill=(35, 35, 35), width=15)
        draw.rectangle((105, 95, 795, 370), fill=(255, 250, 220), outline=(35, 35, 35), width=8)
        _center(draw, image, title, medium, fill=(35, 35, 35), y=145)
    elif template == "panda":
        image.paste((245, 245, 245), (0, 0, width, height))
        draw.ellipse((275, 115, 625, 490), fill=(255, 255, 255), outline=(20, 20, 20), width=8)
        draw.ellipse((270, 90, 350, 180), fill=(20, 20, 20))
        draw.ellipse((550, 90, 630, 180), fill=(20, 20, 20))
        draw.ellipse((330, 235, 430, 335), fill=(20, 20, 20))
        draw.ellipse((470, 235, 570, 335), fill=(20, 20, 20))
        draw.ellipse((390, 310, 510, 395), fill=(20, 20, 20))
        _center(draw, image, title, medium, fill=(20, 20, 20), y=12)
    elif template == "doge":
        image.paste((225, 190, 120), (0, 0, width, height))
        draw.ellipse((240, 135, 660, 550), fill=(195, 125, 65), outline=(80, 45, 25), width=8)
        draw.polygon(((255, 220), (185, 55), (355, 150)), fill=(195, 125, 65), outline=(80, 45, 25))
        draw.polygon(((645, 220), (715, 55), (545, 150)), fill=(195, 125, 65), outline=(80, 45, 25))
        _draw_face(draw, 450, 330, 130)
        _center(draw, image, title, medium, fill=(255, 255, 255), y=15, stroke=2)
    elif template == "shocked":
        image.paste((255, 215, 95), (0, 0, width, height))
        _draw_face(draw, 450, 330, 175, shocked=True)
        _center(draw, image, title, medium, fill=(100, 20, 20), y=20, stroke=1)
    elif template == "rainbow":
        colors = ((240, 70, 70), (245, 150, 50), (250, 225, 80), (80, 190, 100), (75, 160, 230), (150, 100, 210))
        band = height // len(colors)
        for i, color in enumerate(colors):
            draw.rectangle((0, i * band, width, (i + 1) * band), fill=color)
        _center(draw, image, title, big, fill=(255, 255, 255), stroke=3)
    else:
        image.paste((45, 55, 100), (0, 0, width, height))
        draw.rectangle((70, 80, 830, 570), outline=(255, 210, 80), width=8)
        draw.text((100, 105), "今日份梗图", font=small, fill=(255, 210, 80))
        _center(draw, image, title, big, fill=(255, 255, 255), stroke=2)

    return image


def _make_image(template: str, text: str) -> Path:
    pillow = _load_pillow()
    if pillow is None:
        raise RuntimeError("Pillow 未安装")
    Image, ImageDraw, ImageFont = pillow
    image = _render(template, text, Image, ImageDraw, ImageFont)
    path = Path(tempfile.gettempdir()) / f"qqbot_meme_{uuid.uuid4().hex}.png"
    image.save(path, format="PNG")
    return path


async def _send_image(bot: Bot, event: MessageEvent, path: Path) -> None:
    segment = MessageSegment.image(file=str(path))
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        await bot.send_group_msg(group_id=group_id, message=segment)
    else:
        await bot.send_private_msg(user_id=event.user_id, message=segment)


async def _send_text(bot: Bot, event: MessageEvent, message: str) -> None:
    group_id = getattr(event, "group_id", None)
    if group_id is not None:
        await bot.send_group_msg(group_id=group_id, message=message)
    else:
        await bot.send_private_msg(user_id=event.user_id, message=message)


@meme_templates.handle()
async def handle_meme_templates(bot: Bot, event: MessageEvent) -> None:
    await _send_text(
        bot,
        event,
        f"Meme 模板列表：\n{_TEMPLATE_HELP}\n\n用法：/meme 模板 文字",
    )


@meme.handle()
async def handle_meme(
    bot: Bot,
    event: MessageEvent,
    args: Message = CommandArg(),
) -> None:
    raw = args.extract_plain_text().strip()
    if not raw or raw.lower() in {"模板", "模板列表", "list", "help", "帮助"}:
        await _send_text(bot, event, f"用法：/meme 模板 文字\n可用模板：{_TEMPLATE_HELP}")
        return

    parts = raw.split(maxsplit=1)
    if len(parts) == 1:
        template_key, text = "经典", parts[0]
    else:
        template_key, text = parts
    template = _TEMPLATES.get(template_key.lower(), _TEMPLATES.get(template_key, "classic"))
    text = text.strip()[:120]
    if not text:
        text = "今天也要开心喵"

    try:
        path = _make_image(template, text)
        try:
            await _send_image(bot, event, path)
        finally:
            path.unlink(missing_ok=True)
    except Exception:
        await _send_text(bot, event, "梗图生成失败，请确认已安装 Pillow：python -m pip install pillow")
