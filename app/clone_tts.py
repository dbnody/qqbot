"""克隆音色合成：把文本和参考音频一起发给自建 TTS 服务。

默认按 GPT-SoVITS v2 的 /tts 接口写（JSON 里带 ref_audio_path），
换别的服务只改 `_payload()`。没配 VOICE_CLONE_URL 时返回 None，
调用方自动回落到 edge-tts，所以"录了音色但没起服务"不会让机器人哑掉。

环境变量：
    VOICE_CLONE_URL   http://127.0.0.1:9880/tts
    VOICE_CLONE_LANG  文本语言，默认 zh
    VOICE_CLONE_TIMEOUT 秒，默认 30
"""

from __future__ import annotations

import base64
import hashlib
import os

from nonebot import logger


def endpoint() -> str:
    return os.getenv("VOICE_CLONE_URL", "").strip()


def enabled() -> bool:
    return bool(endpoint())


def _payload(text: str, profile: dict[str, str]) -> dict[str, object]:
    return {
        "text": text,
        "text_lang": os.getenv("VOICE_CLONE_LANG", "zh"),
        "ref_audio_path": profile["ref_path"],
        "prompt_text": profile.get("prompt_text", ""),
        "prompt_lang": "zh",
        "media_type": "wav",
        "streaming_mode": False,
    }


def _target(text: str, profile: dict[str, str]):
    from app.tts import tts_dir

    key = hashlib.sha1(f"{profile['ref_path']}|{text}".encode()).hexdigest()[:16]
    return tts_dir() / f"clone_{key}.wav"


async def synthesize_clone(text: str, profile: dict[str, str] | None):
    """克隆合成；未配置或失败返回 None，由调用方回落。"""
    url = endpoint()
    if not url or not profile:
        return None
    target = _target(text, profile)
    if target.exists() and target.stat().st_size > 1024:
        return target

    import httpx

    timeout = float(os.getenv("VOICE_CLONE_TIMEOUT", "30") or 30)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=_payload(text, profile))
        if response.status_code != 200:
            logger.warning(f"[TTS] 克隆服务返回 {response.status_code}")
            return None
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            payload = response.json()
            encoded = payload.get("data") or payload.get("audio") or ""
            if not encoded:
                logger.warning("[TTS] 克隆服务没给音频")
                return None
            target.write_bytes(base64.b64decode(encoded))
        else:
            target.write_bytes(response.content)
        if target.stat().st_size <= 1024:
            return None
        logger.info(f"[TTS] 克隆合成完成：{target.name}")
        return target
    except Exception as exc:
        logger.warning(f"[TTS] 克隆合成失败：{type(exc).__name__}")
        return None
