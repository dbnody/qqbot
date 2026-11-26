"""自定义音色（内测，未写进帮助菜单）：用户录一段语音，让机器人用那个音色说话。

用法（只在私聊生效）：
    回复一条 5~30 秒的语音，发 /音色 录入
    /音色 试听 你好呀   合成一句听听
    /音色 状态          看当前用的是哪个声音
    /音色 清除          删掉样本，回到默认音色

样本存 data/voices/，合成走 app/clone_tts.py；没配 VOICE_CLONE_URL 时
自动回落到 edge-tts，所以先录入、后起服务也能用。
"""

from __future__ import annotations

import base64
from pathlib import Path

import httpx
from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from app import clone_tts, voice_profile
from app.tts import synthesize


voice_cmd = on_command("音色", aliases={"声线"}, priority=5, block=True)

USAGE = (
    "自定义音色还在内测，用法：\n"
    "1) 私聊发一条 5~30 秒的语音，说话清楚、没背景音\n"
    "2) 回复那条语音发 /音色 录入\n"
    "3) /音色 试听 你好呀 听听效果\n"
    "4) /音色 状态 / /音色 清除\n"
    "音色只对你自己这个私聊生效，群里和别的人都不受影响。"
)

AUDIO_SUFFIXES = {".wav", ".mp3", ".silk", ".amr", ".ogg", ".m4a", ".flac", ".aac"}


def _scope(event: MessageEvent) -> str:
    return f"private:{event.user_id}"


def _suffix(*names: str) -> str:
    for name in names:
        if not name or name.startswith("base64://"):
            continue
        suffix = Path(name.split("?")[0].split("#")[0]).suffix.lower()
        if suffix in AUDIO_SUFFIXES:
            return suffix
    return ".wav"


def _record_of(event: MessageEvent) -> MessageSegment | None:
    """当前消息或它回复的那条消息里的语音段。"""
    messages = [event.get_message()]
    reply = getattr(event, "reply", None)
    if reply is not None:
        messages.append(reply.message)
    for message in messages:
        for segment in message:
            if segment.type == "record":
                return segment
    return None


async def _fetch(segment: MessageSegment) -> bytes:
    data = segment.data
    url = str(data.get("url") or "")
    file = str(data.get("file") or "")
    if url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content
    if file.startswith("base64://"):
        return base64.b64decode(file[9:])
    for candidate in (file, url):
        if not candidate:
            continue
        path = _local_path(candidate)
        if path is not None and path.exists():
            return path.read_bytes()
    raise ValueError("拿不到这条语音，换成直接发语音试试")


def _local_path(value: str) -> Path | None:
    """file:///C:/x.wav、C:/x.wav、/root/x.wav 都转成本地路径。"""
    if value.startswith("file:"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        return Path(url2pathname(urlparse(value).path))
    if "://" in value:
        return None
    return Path(value)


@voice_cmd.handle()
async def handle_voice_profile(event: MessageEvent, args=CommandArg()) -> None:
    if isinstance(event, GroupMessageEvent):
        await voice_cmd.finish("音色设置只在私聊里用，群里不接这个。")

    text = args.extract_plain_text().strip()
    scope = _scope(event)

    if text.startswith(("录入", "保存", "设置")):
        segment = _record_of(event)
        if segment is None:
            await voice_cmd.finish(f"没找到语音。先发一条语音，再回复它发 /音色 录入。\n\n{USAGE}")
        try:
            raw = await _fetch(segment)
            path = voice_profile.save_sample(
                scope, raw, _suffix(str(segment.data.get("file") or ""), str(segment.data.get("url") or ""))
            )
        except ValueError as exc:
            await voice_cmd.finish(f"录入失败：{exc}")
        except Exception as exc:
            logger.warning(f"[音色] 样本保存失败：{type(exc).__name__}")
            await voice_cmd.finish("录入失败，重新发一条语音再试。")
        else:
            ready = "克隆服务已就绪" if clone_tts.enabled() else "克隆服务还没配，样本先存着，配好后自动生效"
            await voice_cmd.finish(f"音色样本存好了（{path.stat().st_size // 1024}KB）。{ready}。")

    elif text.startswith(("试听", "听听", "测试")):
        if voice_profile.get_profile(scope) is None:
            await voice_cmd.finish("你还没录过音色。发一条语音，回复它发 /音色 录入。")
        sample = text.removeprefix("试听").removeprefix("听听").removeprefix("测试").strip(" ：:") or "你好呀，我现在是这个声音。"
        audio = await synthesize(sample, None, scope)
        if audio is None:
            await voice_cmd.finish("合成失败了，检查一下克隆服务或网络。")
        await voice_cmd.finish(Message(MessageSegment.record(Path(audio).resolve().as_uri())))

    elif text.startswith(("清除", "删除", "重置")):
        removed = voice_profile.clear(scope)
        await voice_cmd.finish("音色样本删掉了，回到默认声音。" if removed else "本来就没录过音色。")

    else:
        await voice_cmd.finish(f"{voice_profile.describe(scope)}\n\n{USAGE}")
