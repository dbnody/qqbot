"""大肥鱼表情包：把「鲸鱼娘」（DeepSeek 娘）那套 100 张 GIF 同步到本地。

素材来源：https://github.com/diwer/ai-biaoqingbao （非商业二创，见其 NOTICE）
每张图的说明在 catalog.json 里，按说明归到 15 个情绪目录，文件名加 dfy- 前缀，
stickers.pick() 会优先挑这些图，而不是 QQ 原生表情。
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
from nonebot.log import logger

from .stickers import EMOTIONS, FETCH_TAG, IMAGE_SUFFIXES, fetched, normalize, sticker_root

PACK_BASE = "https://raw.githubusercontent.com/diwer/ai-biaoqingbao/master"
CATALOG_URL = f"{PACK_BASE}/docs/catalog.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MIN_BYTES = 2048

# 说明文字里出现这些词就归到对应情绪，先从具体的开始匹配
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("难过", ("委屈", "破防", "裂开", "我没事", "已老实", "求放过", "对不起", "别难过", "心累")),
    ("生气", ("生气", "不服气", "红温", "退退退", "礼貌", "冒犯")),
    ("无语", ("无语", "啊这", "麻了", "不想说话", "大可不必", "嫌弃")),
    ("惊讶", ("震惊", "真的假的", "离谱", "好家伙", "尊嘟假嘟", "那咋了")),
    ("害羞", ("害羞", "紧张")),
    ("得意", ("得意", "拿捏", "满血复活")),
    ("爱心", ("喜欢", "贴贴", "亲亲", "爱你", "想你", "摸摸头", "抱抱", "给你花", "有我在", "期待", "我懂你")),
    ("困", ("困", "晚安", "好累", "充电", "让我缓缓")),
    ("吃饭", ("开饭", "干饭", "饿了", "撑了", "先吃")),
    (
        "摸鱼",
        ("摸鱼", "吃瓜", "看戏", "下班", "上班", "赶工", "开会", "尽力", "太难", "CPU", "救命", "咖啡", "冻住", "热化", "发工资"),
    ),
    (
        "赞",
        ("点赞", "加油", "没问题", "好的", "收到", "明白", "谢谢", "恭喜", "发财", "好运", "欧气", "生日快乐", "周末快乐", "安排了", "辛苦", "拜托"),
    ),
    ("再见", ("再见", "撤退")),
    ("疑惑", ("疑惑", "在吗", "来了", "确认眼神", "等一下", "马上到")),
    ("笑哭", ("笑死", "绷不住")),
    ("笑", ("开心", "哈哈哈", "偷笑", "早安")),
)

_synced = False
_lock = asyncio.Lock()


def enabled() -> bool:
    return os.getenv("STICKER_AUTO_FETCH", "true").strip().lower() not in {"0", "false", "off"}


def emotion_for(label: str) -> str:
    """把素材说明归到一个标准情绪，认不出就当「笑」。"""
    raw = (label or "").strip()
    if raw in EMOTIONS:
        return raw
    for emotion, keywords in RULES:
        if any(word in raw for word in keywords):
            return emotion
    return normalize(raw) or "笑"


def _client() -> httpx.AsyncClient:
    # trust_env=False：环境里的代理变量有的 httpx 版本解析不了
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=HEADERS, trust_env=False)


async def _catalog(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get(CATALOG_URL)
    response.raise_for_status()
    return response.json()


async def sync(force: bool = False) -> dict[str, int]:
    """补齐整套表情包，返回 {情绪: 新下载张数}；网络不通就安静返回空。"""
    if not force and all(fetched(emotion) for emotion in EMOTIONS):
        return {}  # 每个情绪都有图了，不用再联网
    try:
        async with _client() as client:
            catalog = await _catalog(client)
            added: dict[str, int] = {}
            for item in catalog:
                emotion = emotion_for(item.get("label", ""))
                folder = sticker_root() / emotion
                folder.mkdir(parents=True, exist_ok=True)
                target = folder / f"{FETCH_TAG}{item['id']}.gif"
                if target.exists() and target.stat().st_size > MIN_BYTES and not force:
                    continue
                response = await client.get(f"{PACK_BASE}/stickers/512/{item['id']}.gif")
                if response.status_code != 200 or len(response.content) < MIN_BYTES:
                    continue
                target.write_bytes(response.content)
                added[emotion] = added.get(emotion, 0) + 1
    except Exception as exc:
        logger.warning(f"[表情] 同步大肥鱼表情包失败：{type(exc).__name__}")
        return {}
    total = sum(added.values())
    if total:
        logger.info(f"[表情] 新同步 {total} 张大肥鱼表情")
    return added


async def ensure_pack(emotion: str, timeout: float = 30.0) -> Path | None:
    """这个情绪还没有大肥鱼图时，把整套同步一次；一个进程只同步一次。"""
    global _synced
    if not enabled():
        return None
    canonical = normalize(emotion)
    if not canonical or _synced:
        return None
    async with _lock:
        if _synced:
            return None
        _synced = True
    try:
        await asyncio.wait_for(sync(), timeout=timeout)
    except Exception as exc:
        logger.debug(f"[表情] 同步失败：{type(exc).__name__}")
    folder = sticker_root() / canonical
    if not folder.is_dir():
        return None
    found = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.name.startswith(FETCH_TAG)
    ]
    return found[0] if found else None
