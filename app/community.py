"""群聊统计、词云和轻量互动游戏的业务逻辑。

统计数据保存在 SQLite，小游戏状态保存在内存中；重启 Bot 后统计不会丢失，
进行中的小游戏会结束并可重新创建。
"""

from __future__ import annotations

import random
import re
import textwrap
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.database import get_connection


def _nickname(event) -> str:
    sender = event.sender
    return str(getattr(sender, "card", None) or getattr(sender, "nickname", None) or "群友")


def record_group_message(group_id: str, user_id: str, nickname: str, text: str) -> None:
    """保存一条群消息；空消息（例如纯图片）也计入发言次数。"""
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO group_messages (group_id, user_id, nickname, message_text, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(group_id), str(user_id), nickname[:80], text[:4000], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


def _since(days: int) -> str:
    days = max(1, min(days, 365))
    return (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d 00:00:00")


def group_statistics(group_id: str, days: int = 1) -> dict[str, object]:
    """返回群消息总数、活跃人数和时间范围。"""
    start = _since(days)
    with get_connection() as connection:
        total = connection.execute(
            "SELECT COUNT(*) AS n FROM group_messages WHERE group_id = ? AND created_at >= ?",
            (str(group_id), start),
        ).fetchone()["n"]
        users = connection.execute(
            "SELECT COUNT(DISTINCT user_id) AS n FROM group_messages WHERE group_id = ? AND created_at >= ?",
            (str(group_id), start),
        ).fetchone()["n"]
    return {"days": days, "messages": int(total), "users": int(users)}


def speaking_ranking(group_id: str, days: int = 7, limit: int = 10) -> list[dict[str, object]]:
    start = _since(days)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT user_id, MAX(nickname) AS nickname, COUNT(*) AS count
            FROM group_messages
            WHERE group_id = ? AND created_at >= ?
            GROUP BY user_id
            ORDER BY count DESC, MAX(id) ASC
            LIMIT ?
            """,
            (str(group_id), start, max(1, min(limit, 20))),
        ).fetchall()
    return [dict(row) for row in rows]


_STOP_WORDS = set("我们 你我 他们 这个 那个 一个 没有 可以 还是 但是 然后 以及 不是 什么 怎么 真的 现在 进行 回复 你好 哈哈 呵呵".split())


def _word_counter(group_id: str, days: int) -> Counter[str]:
    start = _since(days)
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT message_text FROM group_messages WHERE group_id = ? AND created_at >= ?",
            (str(group_id), start),
        ).fetchall()
    counter: Counter[str] = Counter()
    for row in rows:
        text = str(row["message_text"] or "")
        if text.lstrip().startswith(("/", "!", "！")):
            continue
        text = re.sub(r"https?://\S+|\[CQ:[^\]]+\]", " ", text)
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_]{1,}|[\u4e00-\u9fff]{2,}", text):
            if re.fullmatch(r"[\u4e00-\u9fff]+", word):
                # 没有额外安装分词库时，以二字词统计，适合群聊短语。
                for index in range(len(word) - 1):
                    piece = word[index : index + 2]
                    if piece not in _STOP_WORDS:
                        counter[piece] += 1
            elif word.lower() not in _STOP_WORDS:
                counter[word.lower()] += 1
    return counter


def _font(size: int, bold: bool = False):
    names = ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf")
    if not bold:
        names = names[1:]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def render_word_cloud(group_id: str, days: int = 7) -> Path | None:
    counter = _word_counter(group_id, days)
    if not counter:
        return None
    output_dir = Path("data") / "wordcloud"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"wordcloud_{group_id}_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
    image = Image.new("RGB", (900, 600), (247, 250, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 899, 599), outline=(74, 105, 160), width=3)
    draw.text((30, 22), f"群聊词云 · 最近 {days} 天", font=_font(28, True), fill=(35, 54, 95))
    colors = ((42, 91, 145), (40, 130, 113), (194, 94, 62), (119, 78, 154), (180, 123, 36))
    items = counter.most_common(45)
    max_count = items[0][1]
    randomizer = random.Random(f"{group_id}:{datetime.now():%Y-%m-%d}")
    placed: list[tuple[int, int, int, int]] = []
    for index, (word, count) in enumerate(items):
        size = max(20, min(68, int(22 + 46 * count / max_count)))
        font = _font(size, size >= 42)
        box = draw.textbbox((0, 0), word, font=font)
        width, height = box[2] - box[0], box[3] - box[1]
        position = None
        for _ in range(80):
            x = randomizer.randint(25, max(25, 875 - width))
            y = randomizer.randint(85, max(85, 565 - height))
            candidate = (x - 4, y - 3, x + width + 4, y + height + 3)
            if not any(candidate[0] < old[2] and candidate[2] > old[0] and candidate[1] < old[3] and candidate[3] > old[1] for old in placed):
                position = (x, y)
                placed.append(candidate)
                break
        if position is None:
            continue
        draw.text(position, word, font=font, fill=colors[index % len(colors)])
    image.save(output, format="PNG", optimize=True)
    return output


@dataclass
class RiddleRound:
    question: str
    answer: str
    hint: str


RIDDLES = (
    RiddleRound("什么东西越洗越脏？", "水", "生活中经常用来清洁别人的东西。"),
    RiddleRound("有头没有颈，有眼没有眉，是什么？", "瓶子", "厨房里常见的容器。"),
    RiddleRound("什么门永远关不上？", "球门", "和运动有关。"),
    RiddleRound("小明从一楼走到三楼用了两分钟，照同样速度到五楼要几分钟？", "四分钟", "每上两层需要两分钟。"),
    RiddleRound("什么东西打破了才能用？", "鸡蛋", "早餐中常见。"),
)


IDIOMS = {
    "一心一意", "意气风发", "发扬光大", "大快人心", "心想事成", "成千上万", "万紫千红",
    "红红火火", "火上加油", "油然而生", "生龙活虎", "虎虎生威", "威风凛凛", "凛然正气",
    "气象万千", "千军万马", "马到成功", "功成名就", "就事论事", "事半功倍", "倍道而进",
    "进退两难", "难能可贵", "贵人多忘事", "事与愿违", "违心之论", "论功行赏", "赏心悦目",
    "目不转睛", "精益求精", "精打细算", "算无遗策", "策马扬鞭", "鞭长莫及", "及锋而试",
}


SONGS = (
    ("晴天", "周杰伦", "故事的小黄花，从出生那年就飘着"),
    ("后来", "刘若英", "后来我总算学会了如何去爱"),
    ("稻香", "周杰伦", "还记得你说家是唯一的城堡"),
    ("平凡之路", "朴树", "我曾经跨过山和大海，也穿过人山人海"),
    ("起风了", "买辣椒也用券", "我曾难自拔于世界之大，也沉溺于其中梦话"),
)


RIDDLE_ROUNDS: dict[str, RiddleRound] = {}
IDIOM_ROUNDS: dict[str, str] = {}
DRAW_ROUNDS: dict[str, dict[str, object]] = {}
SONG_ROUNDS: dict[str, tuple[str, str, str]] = {}


def clear_game_rounds(group_id: str, keep: str = "") -> None:
    """确保一个群同一时间只进行一种猜谜游戏。"""
    group_id = str(group_id)
    if keep != "riddle":
        RIDDLE_ROUNDS.pop(group_id, None)
    if keep != "idiom":
        IDIOM_ROUNDS.pop(group_id, None)
    if keep != "draw":
        DRAW_ROUNDS.pop(group_id, None)
    if keep != "song":
        SONG_ROUNDS.pop(group_id, None)


def new_riddle(group_id: str) -> RiddleRound:
    round_ = random.choice(RIDDLES)
    RIDDLE_ROUNDS[str(group_id)] = round_
    return round_


def new_idiom_round(group_id: str) -> str:
    start = random.choice(tuple(IDIOMS))
    IDIOM_ROUNDS[str(group_id)] = start
    return start


def new_song_round(group_id: str) -> tuple[str, str, str]:
    song = random.choice(SONGS)
    SONG_ROUNDS[str(group_id)] = song
    return song


def normalize_answer(text: str) -> str:
    """统一小游戏答案中的空格、标点和常见数字写法。"""
    normalized = re.sub(r"[\s，。！？!?,.、]", "", text).lower()
    return normalized.replace("四", "4").replace("三", "3").replace("二", "2").replace("一", "1")
