"""自定义音色（内测，未写进帮助菜单）：用户录一段语音，机器人就用那个音色说话。

用法（只在私聊生效）：
    回复一条 10~20 秒的语音，发 /音色 录入 我刚才说的这句话
    /音色 文本 我刚才说的这句话   补/改参考文字（不改音频）
    /音色 试听 你好呀            合成一句听听
    /音色 状态 / /音色 清除

参考音频和它对应的文字会一起发给克隆模型（CosyVoice2 零样本克隆），
所以"录入"时带上原话效果最好；忘了带就自动用 ASR 转一份。
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
    "自定义音色（内测）：\n"
    "1) 私聊发一条 10~20 秒的语音，说话清楚、别带背景音\n"
    "2) 回复那条语音发 /音色 录入 我刚才说的这句话\n"
    "   后面那句就是音频里的原话，写对了克隆才像；不写我会自动识别\n"
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


def _local_path(value: str) -> Path | None:
    """file:///C:/x.wav、C:/x.wav、/root/x.wav 都转成本地路径。"""
    if value.startswith("file:"):
        from urllib.parse import urlparse
        from urllib.request import url2pathname

        return Path(url2pathname(urlparse(value).path))
    if "://" in value:
        return None
    return Path(value)


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


async def _preview(text: str, scope: str) -> MessageSegment | None:
    audio = await synthesize(text, None, scope)
    if audio is None:
        return None
    return MessageSegment.record(Path(audio).resolve().as_uri())


@voice_cmd.handle()
async def handle_voice_profile(event: MessageEvent, args=CommandArg()) -> None:
    if isinstance(event, GroupMessageEvent):
        await voice_cmd.finish("音色设置只在私聊里用，群里不接这个。")

    text = args.extract_plain_text().strip()
    scope = _scope(event)

    if text.startswith(("录入", "保存", "设置")):
        segment = _record_of(event)
        if segment is None:
            await voice_cmd.finish(f"没找到语音。先发一条语音，再回复它发 /音色 录入 原话。\n\n{USAGE}")
        spoken = text.removeprefix("录入").removeprefix("保存").removeprefix("设置").strip(" ：:，,")
        if not clone_tts.enabled():
            await voice_cmd.finish(
                "克隆声音还没开起来：在 .env 里填 SILICONFLOW_API_KEY（硅基流动）"
                "或 VOICE_CLONE_URL（自建 GPT-SoVITS），重启后就能用。"
            )
        try:
            raw = await _fetch(segment)
        except Exception as exc:
            logger.warning(f"[音色] 下载样本失败：{type(exc).__name__}")
            await voice_cmd.finish("下载这条语音失败了，重新发一条再试。")

        suffix = _suffix(str(segment.data.get("file") or ""), str(segment.data.get("url") or ""))
        if not spoken:
            spoken = await clone_tts.transcribe(raw, f"sample{suffix}")
        try:
            path = voice_profile.save_sample(scope, raw, suffix, spoken)
        except ValueError as exc:
            await voice_cmd.finish(f"录入失败：{exc}")

        note = f"参考文字：{spoken[:30]}" if spoken else "没识别出文字，效果会差一点，用 /音色 文本 <原话> 补一下。"
        preview = await _preview("音色录好啦，你听听像不像。", scope)
        head = f"音色样本存好了（{path.stat().st_size // 1024}KB）。{note}"
        if preview is None:
            await voice_cmd.finish(f"{head}\n合成没成功，检查一下网络或额度。")
        await voice_cmd.finish(Message(MessageSegment.text(f"{head}\n试听：")) + preview)

    elif text.startswith(("试听", "听听", "测试")):
        if not clone_tts.enabled():
            await voice_cmd.finish("克隆声音还没开起来，先配 SILICONFLOW_API_KEY 或 VOICE_CLONE_URL。")
        if voice_profile.get_profile(scope) is None:
            await voice_cmd.finish("你还没录过音色。发一条语音，回复它发 /音色 录入 原话。")
        sample = text.removeprefix("试听").removeprefix("听听").removeprefix("测试").strip(" ：:，,")
        sample = sample or "你好呀，我现在是这个声音。"
        preview = await _preview(sample, scope)
        if preview is None:
            await voice_cmd.finish("合成失败了，检查一下克隆服务或网络。")
        await voice_cmd.finish(preview)

    elif text.startswith(("文本", "原话", "转写")):
        spoken = text.removeprefix("文本").removeprefix("原话").removeprefix("转写").strip(" ：:，,")
        if not spoken:
            await voice_cmd.finish("用法：/音色 文本 你那条语音里说的是什么")
        if not voice_profile.set_transcript(scope, spoken):
            await voice_cmd.finish("还没录过音色，先发语音发 /音色 录入。")
        await voice_cmd.finish(f"参考文字改好了：{spoken[:30]}。再 /音色 试听 听听看。")

    elif text.startswith(("清除", "删除", "重置")):
        removed = voice_profile.clear(scope)
        await voice_cmd.finish("音色样本删掉了，回到默认声音。" if removed else "本来就没录过音色。")

    else:
        await voice_cmd.finish(f"{voice_profile.describe(scope)}\n{clone_tts.status()}\n\n{USAGE}")
