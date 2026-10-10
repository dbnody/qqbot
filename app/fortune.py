"""今日运势和塔罗牌业务逻辑、图片渲染。"""

from __future__ import annotations

import hashlib
import random
import textwrap
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FORTUNE_LEVELS = (
    ("大吉", "今天适合主动推进重要事项，容易遇到愿意帮助你的人。"),
    ("吉", "今天整体顺利，保持耐心，按计划完成一件重要的小事。"),
    ("中吉", "今天有小惊喜，但不要急于求成，稳步行动会更有收获。"),
    ("平", "今天适合整理和休息，先把手边的事情做好，再考虑下一步。"),
)
LUCKY_COLORS = ("青绿色", "宝蓝色", "暖黄色", "紫色", "米白色", "橙色")


def daily_fortune(user_id: str, nickname: str) -> dict[str, object]:
    """生成同一用户当天稳定一致的运势。"""
    today = date.today().isoformat()
    seed = int(hashlib.sha256(f"{today}:{user_id}".encode()).hexdigest(), 16)
    generator = random.Random(seed)
    level, advice = generator.choice(FORTUNE_LEVELS)
    return {
        "date": today,
        "nickname": nickname,
        "level": level,
        "score": generator.randint(60, 98),
        "advice": advice,
        "lucky_color": generator.choice(LUCKY_COLORS),
        "lucky_number": generator.randint(1, 99),
    }


@dataclass(frozen=True)
class TarotCard:
    number: str
    name: str
    upright: str
    reversed: str
    keyword: str


TAROT_CARDS = (
    TarotCard("0", "愚者", "新的开始、自由、勇气", "鲁莽、准备不足、逃避责任", "相信旅程，但别忘了看路"),
    TarotCard("I", "魔术师", "行动力、创造力、资源整合", "分心、操控、能力未被使用", "你手中已经有足够的工具"),
    TarotCard("II", "女祭司", "直觉、内在智慧、等待时机", "忽视直觉、秘密、信息不足", "安静下来，答案会浮现"),
    TarotCard("III", "皇后", "丰盛、滋养、创造、成长", "过度依赖、停滞、忽略自己", "给正在成长的事物一点时间"),
    TarotCard("IV", "皇帝", "秩序、责任、领导力、稳定", "控制欲、僵化、权威冲突", "建立边界，再承担责任"),
    TarotCard("V", "教皇", "传统、学习、指引、信念", "固执、盲从、拒绝新观点", "向可靠的前辈或知识请教"),
    TarotCard("VI", "恋人", "选择、合作、吸引、价值一致", "犹豫、失衡、沟通不畅", "诚实面对自己的真实选择"),
    TarotCard("VII", "战车", "胜利、决心、推进、掌控方向", "失控、急躁、目标分散", "把力量集中到一个方向"),
    TarotCard("VIII", "力量", "耐心、勇气、温柔的坚持", "自我怀疑、压抑、情绪失控", "真正的力量不必大声证明"),
    TarotCard("IX", "隐者", "独处、反思、寻找答案", "孤立、逃避、拒绝帮助", "暂时慢下来并不等于落后"),
    TarotCard("X", "命运之轮", "转机、变化、周期、新机会", "抗拒变化、反复、时机未到", "顺势而为，留意意外机会"),
    TarotCard("XI", "正义", "公平、因果、清晰判断", "偏见、逃避后果、失衡", "用事实和长期影响做决定"),
    TarotCard("XII", "倒吊人", "换角度、暂停、放下执念", "拖延、无谓牺牲、停滞", "改变视角，可能看到新的出口"),
    TarotCard("XIII", "死神", "结束、转化、告别旧阶段", "抗拒改变、拖延结束、停留过去", "结束是为新阶段腾出空间"),
    TarotCard("XIV", "节制", "平衡、疗愈、协调、耐心", "失衡、过度、节奏混乱", "把不同的部分慢慢调和"),
    TarotCard("XV", "恶魔", "欲望、束缚、沉迷、现实诱惑", "挣脱、看见依赖、重新掌控", "确认什么在消耗你的自由"),
    TarotCard("XVI", "高塔", "突变、真相、旧结构瓦解", "逃避变化、延迟冲击、恐惧", "不稳的结构被打破后才能重建"),
    TarotCard("XVII", "星星", "希望、疗愈、灵感、信任未来", "失望、信心不足、能量低落", "保留希望，也给自己实际支持"),
    TarotCard("XVIII", "月亮", "潜意识、想象、未明信息", "迷雾散去、看清恐惧、误会解除", "先核实信息，再做结论"),
    TarotCard("XIX", "太阳", "成功、快乐、清晰、活力", "短暂低落、过度乐观、延迟", "坦率表达会带来温暖回应"),
    TarotCard("XX", "审判", "觉醒、复盘、重新选择", "自我否定、拒绝改变、错过召唤", "回顾过去，然后做出新的决定"),
    TarotCard("XXI", "世界", "完成、整合、圆满、新循环", "未完结、缺少收尾、重复旧课题", "给阶段性成果一个正式的结束"),
)


def draw_tarot_card() -> tuple[TarotCard, bool]:
    """随机抽取一张大阿尔卡那牌和正逆位。"""
    generator = random.SystemRandom()
    return generator.choice(TAROT_CARDS), generator.choice((False, True))


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.ImageFont, fill: str) -> None:
    box = draw.textbbox((0, 0), text, font=font)
    x = (720 - (box[2] - box[0])) // 2
    draw.text((x, y), text, font=font, fill=fill)


def render_tarot_card(card: TarotCard, reversed_card: bool, user_id: str) -> Path:
    """渲染塔罗牌 PNG，并返回本地路径。"""
    output_dir = Path("data") / "tarot"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"tarot_{user_id}_{stamp}.png"

    background = (247, 237, 211)
    ink = (47, 37, 56)
    gold = (173, 119, 38)
    image = Image.new("RGB", (720, 960), background)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((18, 18, 702, 942), radius=24, outline=gold, width=8)
    draw.rounded_rectangle((38, 38, 682, 922), radius=18, outline=ink, width=2)

    _draw_centered(draw, "TAROT · 今日启示", 72, _font(28, bold=True), gold)
    _draw_centered(draw, f"{card.number} · {card.name}", 130, _font(48, bold=True), ink)
    _draw_centered(draw, "逆位" if reversed_card else "正位", 205, _font(30), (142, 67, 82) if reversed_card else gold)

    center = (360, 430)
    draw.ellipse((170, 250, 550, 630), outline=gold, width=5)
    draw.ellipse((190, 270, 530, 610), outline=ink, width=2)
    # 用几何图形构成每张牌的抽象视觉，避免依赖外部图片资源。
    if reversed_card:
        draw.polygon([(center[0], 560), (265, 370), (455, 370)], outline=ink, fill=(224, 191, 160))
    else:
        draw.polygon([(center[0], 300), (265, 490), (455, 490)], outline=ink, fill=(224, 191, 160))
    draw.ellipse((305, 390, 415, 500), outline=gold, width=5)
    draw.line((250, 440, 470, 440), fill=gold, width=3)
    draw.line((360, 330, 360, 550), fill=gold, width=3)

    _draw_centered(draw, f"关键词：{card.keyword}", 665, _font(25, bold=True), ink)
    meaning = card.reversed if reversed_card else card.upright
    lines = textwrap.wrap(f"牌面提示：{meaning}", width=24)
    y = 735
    for line in lines[:3]:
        _draw_centered(draw, line, y, _font(24), ink)
        y += 38
    _draw_centered(draw, "仅供娱乐与自我反思", 865, _font(20), (100, 91, 100))
    image.save(output_path, format="PNG", optimize=True)
    return output_path
