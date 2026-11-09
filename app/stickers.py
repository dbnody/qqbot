"""表情包：优先发本地图片表情，没有素材时退回 QQ 原生表情。

素材目录：data/stickers/<情绪>/*.jpg|png|gif|webp
情绪名固定为一组标准词，模型的输出经 normalize 归一化后再取图。
"""

from __future__ import annotations

import os
import random
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

EMOTIONS = (
    "笑",
    "笑哭",
    "害羞",
    "无语",
    "生气",
    "难过",
    "惊讶",
    "得意",
    "爱心",
    "困",
    "吃饭",
    "摸鱼",
    "赞",
    "再见",
    "疑惑",
)

ALIASES = {
    "开心": "笑",
    "高兴": "笑",
    "哈哈": "笑",
    "大笑": "笑哭",
    "搞笑": "笑哭",
    "233": "笑哭",
    "草": "笑哭",
    "害羞": "害羞",
    "脸红": "害羞",
    "亲亲": "害羞",
    "白眼": "无语",
    "呵呵": "无语",
    "尴尬": "无语",
    "汗": "无语",
    "怒": "生气",
    "愤怒": "生气",
    "委屈": "难过",
    "伤心": "难过",
    "哭": "难过",
    "震惊": "惊讶",
    "吃惊": "惊讶",
    "意外": "惊讶",
    "酷": "得意",
    "坏笑": "得意",
    "喜欢": "爱心",
    "爱你": "爱心",
    "心": "爱心",
    "睡": "困",
    "累": "困",
    "饿": "吃饭",
    "干饭": "吃饭",
    "摸鱼": "摸鱼",
    "赞": "赞",
    "强": "赞",
    "棒": "赞",
    "鼓掌": "赞",
    "拜拜": "再见",
    "挥手": "再见",
    "问号": "疑惑",
    "疑惑": "疑惑",
    "懵": "疑惑",
}

# QQ 原生表情 id（OneBot face 段），作为没有图片素材时的兜底。
FACE_IDS = {
    "笑": "13",
    "笑哭": "13",
    "害羞": "6",
    "无语": "22",
    "生气": "11",
    "难过": "15",
    "惊讶": "14",
    "得意": "4",
    "爱心": "66",
    "困": "25",
    "吃饭": "61",
    "摸鱼": "28",
    "赞": "79",
    "再见": "39",
    "疑惑": "32",
}


def sticker_root() -> Path:
    configured = os.getenv("STICKER_DIR", "").strip()
    root = Path(configured) if configured else PROJECT_ROOT / "data" / "stickers"
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    return root


def normalize(emotion: str) -> str:
    """把模型给出的情绪词归一化成标准情绪名，识别不了返回空串。"""
    raw = (emotion or "").strip().strip("。，,.!！?？ ")
    if not raw:
        return ""
    if raw in ALIASES:
        return ALIASES[raw]
    if raw in EMOTIONS:
        return raw
    for canonical in EMOTIONS:
        if canonical in raw or raw in canonical:
            return canonical
    return ""


FETCH_TAG = "dfy-"  # sticker_fetch 下载的「大肥鱼」图带这个前缀


def fetched(emotion: str) -> list[Path]:
    """某个情绪下搜来的大肥鱼图。"""
    canonical = normalize(emotion)
    folder = sticker_root() / canonical if canonical else None
    if folder is None or not folder.is_dir():
        return []
    return [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.name.startswith(FETCH_TAG)
    ]


def pick(emotion: str) -> Path | None:
    """从对应情绪目录里随机取一张表情图，优先用搜来的大肥鱼图。"""
    canonical = normalize(emotion)
    if not canonical:
        return None
    folder = sticker_root() / canonical
    if not folder.is_dir():
        return None
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES and p.is_file()]
    if not files:
        return None
    preferred = [p for p in files if p.name.startswith(FETCH_TAG)]
    return random.choice(preferred or files)


def face(emotion: str) -> str | None:
    return FACE_IDS.get(normalize(emotion))


def packs() -> dict[str, int]:
    """统计每个情绪目录里的素材数量，供 /表情 命令展示。"""
    root = sticker_root()
    if not root.is_dir():
        return {}
    return {
        folder.name: sum(
            1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES
        )
        for folder in sorted(root.iterdir())
        if folder.is_dir()
    }
