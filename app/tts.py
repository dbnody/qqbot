"""文字转语音：edge-tts 在线神经语音为主，Windows SAPI 离线兜底。

生成的音频放在 data/tts/ 下，按文本哈希缓存，2 小时后自动清理。
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from pathlib import Path

from nonebot import logger


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _enabled() -> bool:
    return os.getenv("TTS_ENABLED", "true").strip().lower() not in {"0", "false", "off", "no"}


def _engine() -> str:
    return os.getenv("TTS_ENGINE", "edge").strip().lower() or "edge"


def default_voice() -> str:
    return os.getenv("TTS_VOICE", "zh-CN-XiaoxiaoNeural").strip() or "zh-CN-XiaoxiaoNeural"


def tts_dir() -> Path:
    path = PROJECT_ROOT / "data" / "tts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def clean_text(text: str) -> str:
    """去掉标签、代码块和链接，只留能读出来的内容。"""
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"[`*_#>\[\]【】]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    limit = int(os.getenv("TTS_MAX_CHARS", "180") or 180)
    return text[:limit]


async def _edge_tts(text: str, voice: str, target: Path) -> bool:
    try:
        import edge_tts
    except ImportError:
        return False
    try:
        communicate = edge_tts.Communicate(text, voice, rate="+0%")
        await asyncio.wait_for(communicate.save(str(target)), timeout=30)
        return target.exists() and target.stat().st_size > 1024
    except Exception as exc:  # 网络或服务异常都退回 SAPI
        logger.warning(f"[TTS] edge-tts 失败：{type(exc).__name__}")
        return False


async def _sapi_tts(text: str, target: Path) -> bool:
    """用系统自带的 System.Speech 合成 WAV，完全离线。"""
    script_path = target.with_suffix(".txt")
    script_path.write_text(text, encoding="utf-8")
    code = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$s.SetOutputToWaveFile('{target}');"
        f"$t = Get-Content -LiteralPath '{script_path}' -Raw -Encoding UTF8;"
        "$s.Speak($t);"
        "$s.Dispose()"
    )
    try:
        process = await asyncio.create_subprocess_exec(
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            code,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=60)
        return target.exists() and target.stat().st_size > 1024
    except Exception as exc:
        logger.warning(f"[TTS] SAPI 合成失败：{type(exc).__name__}")
        return False
    finally:
        script_path.unlink(missing_ok=True)


def _cleanup() -> None:
    cutoff = time.time() - 2 * 3600
    for path in tts_dir().glob("*"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


async def warmup() -> None:
    """预热 edge-tts：冷启动一次要 2s，热了只要 1.2s。

    Bot 启动时后台跑一次，第一条真语音就能少等约一秒。
    """
    if not _enabled() or _engine() not in {"edge", "auto"}:
        return
    try:
        await asyncio.wait_for(synthesize("我在的，随时找我", default_voice()), timeout=20)
        logger.info("[TTS] 语音引擎预热完成")
    except Exception as exc:
        logger.debug(f"[TTS] 预热失败：{type(exc).__name__}")


async def synthesize(text: str, voice: str | None = None) -> Path | None:
    """把文本合成为语音文件；关闭或失败时返回 None。"""
    if not _enabled():
        return None
    spoken = clean_text(text)
    if len(spoken) < 2:
        return None
    voice = voice or default_voice()
    key = hashlib.sha1(f"{voice}|{spoken}".encode()).hexdigest()[:16]
    engine = _engine()
    _cleanup()

    if engine in {"edge", "auto"}:
        mp3 = tts_dir() / f"{key}.mp3"
        if mp3.exists() and mp3.stat().st_size > 1024:
            return mp3
        if await _edge_tts(spoken, voice, mp3):
            logger.info(f"[TTS] edge-tts 合成完成：{mp3.name}")
            return mp3
        if engine == "edge" and os.getenv("TTS_SAPI_FALLBACK", "true").lower() in {"0", "false", "off"}:
            return None

    wav = tts_dir() / f"{key}.wav"
    if wav.exists() and wav.stat().st_size > 1024:
        return wav
    if await _sapi_tts(spoken, wav):
        logger.info(f"[TTS] SAPI 合成完成：{wav.name}")
        return wav
    return None
