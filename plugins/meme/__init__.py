"""本地梗图生成器。

用法：/meme 模板 文字
例如：/meme 哭泣猫猫 今天也要努力上班

画面统一在 900×650 的逻辑坐标里画，内部按 SS 倍超采样再缩回去，所以线条没有锯齿；
背景用渐变/径向光，元素用半透明叠色，整体不再有硬边框。
"""

from __future__ import annotations

import math
import os
import random
import tempfile
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
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

W, H = 900, 650
SS = 2  # 超采样倍数


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
                return ImageFont.truetype(path, size * SS)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, width: int = 15) -> str:
    text = " ".join(text.strip().split())
    return "\n".join(text[i : i + width] for i in range(0, len(text), width))


def _gradient(Image, size: tuple[int, int], top, bottom):
    """垂直线性渐变。"""
    width, height = size
    try:
        import numpy as np
    except ImportError:
        image = Image.new("RGB", size)
        pixels = image.load()
        for y in range(height):
            t = y / max(1, height - 1)
            color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            for x in range(width):
                pixels[x, y] = color
        return image
    t = np.linspace(0.0, 1.0, height)[:, None, None]
    arr = (np.array(top, dtype=float) * (1 - t) + np.array(bottom, dtype=float) * t).astype("uint8")
    return Image.fromarray(np.repeat(arr, width, axis=1), "RGB")


def _radial(Image, size: tuple[int, int], inner, outer, cy: float = 0.45, r: float = 0.85):
    """径向渐变：中心亮、四周暗，用来代替死板的纯色底。"""
    try:
        import numpy as np
    except ImportError:  # 没 numpy 就退回线性渐变，效果差一点但不至于崩
        return _gradient(Image, size, inner, outer)
    width, height = size
    cx = 0.5
    y, x = np.mgrid[0:height, 0:width]
    dist = np.sqrt(((x - cx * width) / (r * width)) ** 2 + ((y - cy * height) / (r * height)) ** 2)
    dist = np.clip(dist, 0.0, 1.0)[..., None]
    arr = (np.array(inner) * (1 - dist) + np.array(outer) * dist).astype("uint8")
    return Image.fromarray(arr, "RGB")


class _Pen:
    """把 900×650 的逻辑坐标换算到超采样画布上，宽高和字号一起放大。"""

    def __init__(self, draw, scale: int) -> None:
        self._d = draw
        self._s = scale

    def _xy(self, xy):
        return (xy[0] * self._s, xy[1] * self._s)

    def _box(self, box):
        return tuple(v * self._s for v in box)

    @staticmethod
    def _kw(kw):
        scaled = dict(kw)
        for key in ("width", "stroke_width"):
            if scaled.get(key):
                scaled[key] = max(1, round(scaled[key] * SS))
        return scaled

    def ellipse(self, box, **kw):
        self._d.ellipse(self._box(box), **self._kw(kw))

    def rectangle(self, box, **kw):
        self._d.rectangle(self._box(box), **self._kw(kw))

    def rounded_rectangle(self, box, radius: int, **kw):
        self._d.rounded_rectangle(self._box(box), radius=radius * SS, **self._kw(kw))

    def polygon(self, points, **kw):
        self._d.polygon([self._xy(p) for p in points], **self._kw(kw))

    def line(self, points, **kw):
        self._d.line([self._xy(p) for p in points], **self._kw(kw))

    def arc(self, box, start, end, **kw):
        self._d.arc(self._box(box), start, end, **self._kw(kw))

    def text(self, xy, text: str, font=None, **kw):
        self._d.text(self._xy(xy), text, font=font, **self._kw(kw))

    def bbox(self, text: str, font):
        return self._d.multiline_textbbox((0, 0), text, font=font, align="center", spacing=8 * SS)


def _center(pen: _Pen, text: str, font, fill, y: float | None = None, shadow: bool = True):
    """逻辑坐标居中排字，带一层柔和投影。"""
    box = pen.bbox(text, font)
    offset = 8 * SS  # multiline_textbbox 的左右留白
    text_w = (box[2] - box[0] - offset) / SS
    text_h = (box[3] - box[1]) / SS
    x = (W - text_w) / 2
    top = y if y is not None else (H - text_h) / 2
    if shadow:
        pen.text((x + 3, top + 4), text, font=font, fill=(0, 0, 0, 110), align="center", spacing=8)
    pen.text((x, top), text, font=font, fill=fill, align="center", spacing=8)


def _glow(image, ellipses, blur: int = 26) -> None:
    """画一批半透明椭圆再整体模糊，避免出现一圈一圈的硬边。"""
    from PIL import Image, ImageDraw, ImageFilter

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pen = _Pen(ImageDraw.Draw(layer), SS)
    for box, fill in ellipses:
        pen.ellipse(box, fill=fill)
    layer = layer.filter(ImageFilter.GaussianBlur(blur * SS))
    image.paste(layer, (0, 0), layer)


def _center_in(pen: _Pen, box, text: str, font, fill, shadow: bool = True):
    """在给定方框里水平垂直居中。"""
    b = pen.bbox(text, font)
    text_w = (b[2] - b[0] - 8 * SS) / SS
    text_h = (b[3] - b[1]) / SS
    x = box[0] + (box[2] - box[0] - text_w) / 2
    y = box[1] + (box[3] - box[1] - text_h) / 2
    if shadow:
        pen.text((x + 3, y + 4), text, font=font, fill=(0, 0, 0, 110), align="center", spacing=8)
    pen.text((x, y), text, font=font, fill=fill, align="center", spacing=8)


def _sparkle(pen: _Pen, x: float, y: float, size: float, color, alpha: int = 220):
    """四角星，用来点缀画面。"""
    fill = (*color, alpha)
    pen.polygon(
        (((x, y - size)), (x + size * 0.28, y - size * 0.28), (x + size, y),
         (x + size * 0.28, y + size * 0.28), (x, y + size),
         (x - size * 0.28, y + size * 0.28), (x - size, y),
         (x - size * 0.28, y - size * 0.28)),
        fill=fill,
    )


def _blush(pen: _Pen, cx: float, cy: float, r: float, color=(255, 140, 150)) -> None:
    pen.ellipse((cx - r, cy - r * 0.55, cx + r, cy + r * 0.55), fill=(*color, 90))


def _card(pen: _Pen, box, fill=(255, 255, 255), alpha: int = 225, radius: int = 26, outline=None):
    pen.rounded_rectangle(box, radius=radius, fill=(*fill, alpha), outline=outline)


def _draw_face(pen: _Pen, cx: int, cy: int, radius: int, color=(250, 214, 178), shocked=False):
    pen.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline=(70, 50, 45), width=4)
    eye_y = cy - radius // 4
    if shocked:
        for dx in (-radius // 3, radius // 3):
            pen.ellipse((cx + dx - 16, eye_y - 20, cx + dx + 16, eye_y + 20), fill=(30, 30, 35))
            pen.ellipse((cx + dx - 8, eye_y - 12, cx + dx + 2, eye_y - 2), fill=(255, 255, 255))
        pen.ellipse((cx - 30, cy + radius // 4, cx + 30, cy + radius // 2), fill=(70, 25, 30))
        pen.ellipse((cx - 16, cy + radius // 3, cx + 16, cy + radius // 2 - 6), fill=(200, 90, 100))
    else:
        for dx in (-radius // 3, radius // 3):
            pen.ellipse((cx + dx - 9, eye_y, cx + dx + 9, eye_y + 18), fill=(40, 35, 35))
            pen.ellipse((cx + dx - 5, eye_y + 2, cx + dx + 1, eye_y + 8), fill=(255, 255, 255))
        pen.arc((cx - radius // 3, cy, cx + radius // 3, cy + radius // 2), 15, 165, fill=(90, 40, 45), width=5)
    _blush(pen, cx - radius * 0.62, cy + radius * 0.22, radius * 0.22)
    _blush(pen, cx + radius * 0.62, cy + radius * 0.22, radius * 0.22)


def _render(template: str, text: str, Image, ImageDraw, ImageFont):
    wide, tall = W * SS, H * SS
    title = _wrap_text(text, 15)
    big = _font(ImageFont, 58)
    medium = _font(ImageFont, 40)
    small = _font(ImageFont, 26)
    tiny = _font(ImageFont, 22)

    if template == "crying_cat":
        image = _radial(Image, (wide, tall), (196, 230, 255), (238, 248, 255), cy=0.28, r=1.0)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        for box in ((70, 70, 300, 140), (560, 50, 830, 120), (330, 30, 520, 86)):
            pen.ellipse(box, fill=(255, 255, 255, 150))
        head = (250, 140, 650, 530)
        pen.polygon(((268, 205), (250, 75), (392, 165)), fill=(250, 206, 176), outline=(228, 160, 140), width=4)
        pen.polygon(((632, 205), (650, 75), (508, 165)), fill=(250, 206, 176), outline=(228, 160, 140), width=4)
        pen.polygon(((292, 190), (280, 112), (368, 165)), fill=(255, 196, 200))
        pen.polygon(((608, 190), (620, 112), (532, 165)), fill=(255, 196, 200))
        pen.ellipse(head, fill=(250, 214, 184), outline=(232, 176, 146), width=4)
        pen.ellipse((352, 396, 548, 486), fill=(255, 244, 236), outline=(240, 214, 200), width=3)
        for x in (334, 494):
            pen.arc((x, 268, x + 72, 336), 200, 340, fill=(92, 62, 58), width=6)
        pen.ellipse((424, 414, 476, 446), fill=(255, 168, 176))
        pen.arc((424, 446, 476, 482), 20, 160, fill=(150, 90, 92), width=4)
        for x in (340, 556):
            pen.polygon(((x, 330), (x + 12, 368), (x - 12, 368)), fill=(126, 196, 246))
            pen.ellipse((x - 14, 364, x + 14, 386), fill=(126, 196, 246))
        _blush(pen, 300, 402, 32)
        _blush(pen, 600, 402, 32)
        _card(pen, (130, 556, 770, 630), fill=(255, 255, 255), alpha=235)
        _center_in(pen, (130, 556, 770, 630), title, medium, (58, 62, 90))

    elif template == "perfect":
        image = _radial(Image, (wide, tall), (255, 246, 176), (86, 190, 110), cy=0.42, r=0.9)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        for i in range(20):
            angle = math.tau * i / 20
            pen.line(((450, 300), (450 + math.cos(angle) * 620, 300 + math.sin(angle) * 620)),
                     fill=(255, 255, 210, 45), width=16)
        for x, y, s in ((120, 110, 22), (780, 140, 18), (150, 500, 16), (800, 470, 20), (700, 60, 12)):
            _sparkle(pen, x, y, s, (255, 250, 190))
        pen.ellipse((296, 110, 604, 418), fill=(255, 214, 66), outline=(255, 246, 190), width=6)
        pen.arc((318, 132, 582, 396), 200, 300, fill=(255, 255, 235, 150), width=10)
        pen.ellipse((382, 208, 412, 244), fill=(120, 78, 20))
        pen.ellipse((490, 208, 520, 244), fill=(120, 78, 20))
        pen.arc((368, 226, 536, 352), 20, 160, fill=(120, 78, 20), width=12)
        _blush(pen, 356, 290, 22)
        _blush(pen, 546, 290, 22)
        _card(pen, (232, 432, 668, 520), fill=(255, 255, 255), alpha=238, radius=22)
        _center_in(pen, (232, 432, 668, 520), title, medium, (56, 96, 48))

    elif template == "masterpiece":
        image = _radial(Image, (wide, tall), (128, 52, 156), (28, 8, 52), cy=0.42, r=0.95)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        for i in range(18):
            angle = math.tau * i / 18
            pen.line(((450, 300), (450 + math.cos(angle) * 640, 300 + math.sin(angle) * 640)),
                     fill=(255, 220, 130, 38), width=14)
        _glow(image, [
            ((250, 130, 650, 470), (255, 238, 180, 120)),
            ((330, 200, 570, 400), (255, 250, 220, 150)),
        ], blur=34)
        _glow(image, [
            ((280, 170, 620, 430), (255, 238, 180, 150)),
            ((360, 230, 540, 370), (255, 250, 220, 170)),
        ], blur=30)
        for x, y, s in ((140, 130, 20), (760, 110, 16), (110, 520, 14), (790, 500, 22), (450, 70, 12)):
            _sparkle(pen, x, y, s, (255, 226, 140))
        _card(pen, (170, 470, 730, 556), fill=(28, 10, 46), alpha=205, radius=26)
        _center_in(pen, (170, 470, 730, 556), title, medium, (255, 238, 200))

    elif template == "pornhub":
        image = _gradient(Image, (wide, tall), (34, 34, 38), (10, 10, 12))
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        pen.rounded_rectangle((70, 160, 830, 400), radius=20, fill=(6, 6, 8, 235))
        pen.rectangle((86, 176, 100, 384), fill=(255, 153, 0))
        pen.rounded_rectangle((700, 186, 790, 236), radius=12, fill=(255, 153, 0, 235))
        pen.text((722, 192), "HD", font=tiny, fill=(24, 24, 24))
        _center(pen, title, medium, (255, 255, 255), y=252)

    elif template == "sign":
        image = _radial(Image, (wide, tall), (255, 238, 206), (247, 186, 128), cy=0.4, r=0.95)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        _glow(image, [((150, 90, 750, 440), (255, 250, 235, 130))], blur=30)
        # 立柱 + 小人：小人站在牌子下面，双手举着立柱
        pen.rectangle((292, 372, 314, 470), fill=(150, 102, 68))
        pen.rectangle((586, 372, 608, 470), fill=(150, 102, 68))
        pen.line(((300, 462), (420, 578)), fill=(252, 214, 178), width=22)
        pen.line(((600, 462), (480, 578)), fill=(252, 214, 178), width=22)
        pen.ellipse((286, 448, 314, 476), fill=(252, 214, 178), outline=(214, 158, 128), width=2)
        pen.ellipse((586, 448, 614, 476), fill=(252, 214, 178), outline=(214, 158, 128), width=2)
        pen.rounded_rectangle((412, 560, 488, 650), radius=28, fill=(86, 132, 196))
        pen.ellipse((402, 452, 498, 548), fill=(252, 214, 178), outline=(214, 158, 128), width=3)
        pen.ellipse((432, 486, 442, 500), fill=(60, 40, 34))
        pen.ellipse((458, 486, 468, 500), fill=(60, 40, 34))
        pen.arc((430, 496, 470, 522), 20, 160, fill=(150, 90, 80), width=3)
        # 牌子最后画，压在手和立柱前面
        pen.rounded_rectangle((130, 100, 770, 380), radius=22, fill=(252, 238, 214), outline=(176, 126, 82), width=6)
        for i in range(5):
            y = 140 + i * 46
            pen.line(((150, y), (750, y)), fill=(214, 168, 128, 70), width=3)
        _center_in(pen, (130, 100, 770, 380), title, medium, (96, 62, 38))

    elif template == "panda":
        image = _radial(Image, (wide, tall), (226, 250, 240), (196, 234, 220), cy=0.36, r=0.95)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        for x, y, s in ((120, 140, 16), (800, 180, 14), (150, 500, 18)):
            _sparkle(pen, x, y, s, (120, 190, 160), alpha=150)
        pen.ellipse((272, 108, 380, 216), fill=(32, 32, 34))
        pen.ellipse((520, 108, 628, 216), fill=(32, 32, 34))
        pen.ellipse((262, 150, 638, 526), fill=(255, 255, 255), outline=(46, 46, 50), width=5)
        pen.ellipse((322, 244, 428, 350), fill=(38, 38, 42))
        pen.ellipse((472, 244, 578, 350), fill=(38, 38, 42))
        for x in (362, 512):
            pen.ellipse((x - 22, 276, x + 22, 320), fill=(255, 255, 255))
            pen.ellipse((x - 12, 286, x + 12, 310), fill=(30, 30, 34))
            pen.ellipse((x - 4, 291, x + 4, 299), fill=(255, 255, 255))
        pen.ellipse((420, 356, 480, 400), fill=(34, 34, 38))
        pen.arc((392, 396, 508, 452), 20, 160, fill=(60, 60, 64), width=5)
        _blush(pen, 330, 372, 30, (255, 168, 176))
        _blush(pen, 570, 372, 30, (255, 168, 176))
        _card(pen, (150, 540, 750, 620), fill=(255, 255, 255), alpha=232)
        _center_in(pen, (150, 540, 750, 620), title, medium, (44, 74, 62))

    elif template == "doge":
        image = _radial(Image, (wide, tall), (255, 244, 210), (247, 206, 148), cy=0.4, r=0.95)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        pen.polygon(((268, 220), (196, 74), (356, 154)), fill=(226, 158, 86), outline=(158, 100, 48), width=4)
        pen.polygon(((632, 220), (704, 74), (544, 154)), fill=(226, 158, 86), outline=(158, 100, 48), width=4)
        pen.ellipse((250, 140, 650, 508), fill=(230, 164, 92), outline=(158, 100, 48), width=4)
        pen.ellipse((338, 356, 562, 480), fill=(252, 232, 206), outline=(222, 186, 150), width=3)
        pen.ellipse((420, 372, 482, 412), fill=(58, 40, 34))
        pen.arc((392, 404, 508, 462), 20, 160, fill=(96, 62, 46), width=5)
        pen.polygon(((430, 452), (470, 452), (458, 486), (442, 486)), fill=(240, 128, 138))
        for x in (348, 512):
            pen.ellipse((x - 12, 276, x + 12, 302), fill=(46, 32, 28))
            pen.ellipse((x - 6, 280, x + 3, 290), fill=(255, 255, 255))
        _blush(pen, 314, 372, 30)
        _blush(pen, 586, 372, 30)
        _card(pen, (150, 540, 750, 620), fill=(255, 250, 238), alpha=232)
        _center_in(pen, (150, 540, 750, 620), title, medium, (110, 66, 34))

    elif template == "shocked":
        image = _radial(Image, (wide, tall), (255, 240, 160), (240, 168, 36), cy=0.42, r=1.0)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        for i in range(24):
            angle = math.tau * i / 24
            pen.line(((450, 320), (450 + math.cos(angle) * 700, 320 + math.sin(angle) * 700)),
                     fill=(255, 255, 240, 40), width=12)
        _glow(image, [
            ((220, 100, 680, 520), (255, 255, 235, 90)),
            ((310, 190, 590, 440), (255, 255, 255, 70)),
        ], blur=28)
        _draw_face(pen, 450, 330, 165, shocked=True)
        for x in (86, 750):
            pen.text((x, 84), "!!", font=_font(ImageFont, 62), fill=(210, 44, 44, 235), stroke_width=2, stroke_fill=(255, 240, 220, 200))
        _card(pen, (150, 556, 750, 626), fill=(255, 253, 240), alpha=228)
        _center_in(pen, (150, 556, 750, 626), title, medium, (150, 40, 40))

    elif template == "rainbow":
        colors = ((240, 74, 74), (246, 146, 48), (250, 222, 84), (96, 196, 112), (72, 158, 232), (148, 104, 214))
        image = _gradient(Image, (wide, tall), (60, 40, 90), (20, 14, 40))
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        band = (H + 80) / len(colors)
        for i, color in enumerate(colors):
            y0 = -80 + i * band
            pen.polygon(((0, y0), (W, y0 + 50), (W, y0 + 50 + band + 3), (0, y0 + band + 3)), fill=(*color, 235))
        pen.polygon(((0, -80), (W, -30), (W, 90), (0, 40)), fill=(255, 255, 255, 40))
        for x, y, s in ((120, 120, 18), (780, 160, 14), (130, 520, 16), (770, 500, 20)):
            _sparkle(pen, x, y, s, (255, 255, 255))
        _center(pen, title, big, (255, 255, 255))

    else:  # classic：不再画硬边框，改成中心柔光 + 角标
        image = _radial(Image, (wide, tall), (58, 74, 132), (16, 20, 42), cy=0.42, r=0.95)
        draw = ImageDraw.Draw(image, "RGBA")
        pen = _Pen(draw, SS)
        _glow(image, [
            ((150, 120, 750, 520), (255, 220, 140, 70)),
            ((250, 190, 650, 450), (255, 226, 160, 60)),
        ], blur=40)
        for x, y, s in ((110, 120, 12), (790, 150, 10), (120, 540, 10), (800, 520, 14), (700, 90, 8), (180, 80, 7)):
            _sparkle(pen, x, y, s, (255, 226, 150), alpha=170)
        pen.rounded_rectangle((66, 60, 268, 108), radius=20, fill=(255, 208, 84, 235))
        pen.text((92, 68), "今日份梗图", font=small, fill=(48, 40, 24))
        _center(pen, title, big, (255, 255, 255))

    return image.resize((W, H), Image.LANCZOS)


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
