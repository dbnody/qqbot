"""点歌：搜索 QQ 音乐和网易云音乐并发送音乐卡片。"""

from __future__ import annotations

import re

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from app.music import SongResult, search_songs


music_command = on_command("点歌", aliases={"点歌台", "music"}, priority=10, block=True)


def _parse_request(raw: str) -> tuple[str, str]:
    text = raw.strip()
    match = re.match(r"^(qq音乐|qq|腾讯音乐|网易云音乐|网易云|网易|163|netease)\s+(.+)$", text, re.I)
    if match:
        platform_text, text = match.group(1).lower(), match.group(2).strip()
        platform = "qq" if platform_text in {"qq音乐", "qq", "腾讯音乐"} else "163"
    else:
        platform = "both"

    # 支持：歌手 歌名、歌手 - 歌名、歌手：周杰伦 歌名：晴天等写法。
    labeled = re.fullmatch(
        r"(?:歌手(?:名)?\s*[:：]\s*(?P<artist>.+?))\s+(?:歌曲?|歌名)\s*[:：]\s*(?P<title>.+)",
        text,
        re.I,
    )
    if labeled:
        text = f"{labeled.group('artist')} {labeled.group('title')}"
    else:
        text = re.sub(r"^(?:歌曲?|歌名)\s*[:：]\s*", "", text, flags=re.I)
        text = re.sub(r"^(?:歌手|歌手名)\s*[:：]\s*", "", text, flags=re.I)
        text = re.sub(r"\s*[-—|]\s*", " ", text, count=1)
    return platform, re.sub(r"\s+", " ", text).strip()


def _card(result: SongResult) -> MessageSegment:
    return MessageSegment.music(result.platform, result.song_id)


@music_command.handle()
async def handle_music(event: MessageEvent, args=CommandArg()) -> None:
    platform, keyword = _parse_request(args.extract_plain_text())
    if not keyword:
        await music_command.finish(
            "用法：/点歌 歌名、歌手名，或“歌手 歌名”（同时搜索两个平台）\n"
            "/点歌 周杰伦 晴天\n"
            "/点歌 qq 歌手：周杰伦 歌名：晴天\n"
            "/点歌 网易云 晴天 - 周杰伦"
        )
    results = await search_songs(keyword, platform)
    if not results:
        name = "QQ 音乐和网易云音乐" if platform == "both" else ("QQ 音乐" if platform == "qq" else "网易云音乐")
        await music_command.finish(f"没有在{name}找到“{keyword}”，请换一个歌名或稍后再试。")

    message = Message([MessageSegment.text(f"为你搜索“{keyword}”：")])
    for result in results:
        label = "QQ 音乐" if result.platform == "qq" else "网易云音乐"
        message += MessageSegment.text(f"\n{label}：{result.title} - {result.artist}\n{result.detail_url}\n")
        message += _card(result)
    await music_command.finish(message)
