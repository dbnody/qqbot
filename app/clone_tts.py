"""克隆音色合成：让 TTS 用用户自己录的那段声音说话。

两条路，按环境变量自动选：

1. siliconflow（默认，有 SILICONFLOW_API_KEY 就用）
   CosyVoice2 零样本克隆：请求里直接带参考音频 + 那段音频对应的文字，
   不用训练、不用建音色 ID、不会过期。
   ASR 用 SenseVoiceSmall，用户懒得打字时自动转出参考文本。

2. http（配了 VOICE_CLONE_URL 时）
   自建 GPT-SoVITS / CosyVoice 的 /tts 接口，参数见 _http_payload。

都没配就返回 None，调用方自动回落到 edge-tts，不会哑火。
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from nonebot import logger


def _base() -> str:
    return os.getenv("SILICONFLOW_API_BASE", "https://api.siliconflow.cn/v1").rstrip("/")


def _key() -> str:
    return os.getenv("SILICONFLOW_API_KEY", "").strip()


def _model() -> str:
    return os.getenv("VOICE_CLONE_MODEL", "FunAudioLLM/CosyVoice2-0.5B").strip()


def provider() -> str:
    explicit = os.getenv("VOICE_CLONE_PROVIDER", "").strip().lower()
    if explicit in {"siliconflow", "http", "none", "off"}:
        return "none" if explicit in {"none", "off"} else explicit
    if os.getenv("VOICE_CLONE_URL", "").strip():
        return "http"
    if _key():
        return "siliconflow"
    return "none"


def enabled() -> bool:
    return provider() != "none"


def status() -> str:
    kind = provider()
    if kind == "siliconflow":
        return f"克隆已就绪（硅基流动 {_model()}）"
    if kind == "http":
        return "克隆已就绪（自建服务）"
    return "克隆没配：填 SILICONFLOW_API_KEY 或 VOICE_CLONE_URL 就能用"


def _target(text: str, profile: dict[str, str]) -> Path:
    from app.tts import tts_dir

    stamp = Path(profile["ref_path"]).stat().st_mtime_ns
    key = hashlib.sha1(f"{profile['ref_path']}|{stamp}|{text}".encode()).hexdigest()[:16]
    return tts_dir() / f"clone_{key}.mp3"


async def transcribe(raw: bytes, filename: str = "sample.wav") -> str:
    """把参考音频转成文字（硅基流动 SenseVoice）；失败返回空串。"""
    if provider() != "siliconflow":
        return ""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{_base()}/audio/transcriptions",
                headers={"Authorization": f"Bearer {_key()}"},
                files={"file": (filename, raw, "application/octet-stream")},
                data={"model": os.getenv("VOICE_CLONE_ASR_MODEL", "FunAudioLLM/SenseVoiceSmall")},
            )
        if response.status_code != 200:
            logger.warning(f"[TTS] 参考音频转文字失败：{response.status_code}")
            return ""
        text = str(response.json().get("text") or "").strip()
        return text[:500]
    except Exception as exc:
        logger.warning(f"[TTS] 参考音频转文字异常：{type(exc).__name__}")
        return ""


async def synthesize_clone(text: str, profile: dict[str, str] | None):
    """用参考音色合成；未配置或失败返回 None，由调用方回落。"""
    kind = provider()
    if kind == "none" or not profile:
        return None
    ref = Path(profile["ref_path"])
    if not ref.exists():
        return None

    target = _target(text, profile)
    if target.exists() and target.stat().st_size > 1024:
        return target

    if kind == "http":
        ok = await _http_tts(text, profile, target)
    else:
        ok = await _siliconflow_tts(text, profile, target)
    if not ok:
        return None
    logger.info(f"[TTS] 克隆合成完成：{target.name}")
    return target


def _ref_uri(ref: Path) -> str:
    encoded = base64.b64encode(ref.read_bytes()).decode()
    suffix = ref.suffix.lower().lstrip(".") or "wav"
    return f"data:audio/{suffix};base64,{encoded}"


async def _siliconflow_tts(text: str, profile: dict[str, str], target: Path) -> bool:
    import httpx

    prompt_text = (profile.get("prompt_text") or "").strip()
    if not prompt_text:
        logger.warning("[TTS] 参考音频缺文字，克隆效果会变差")
    payload = {
        "model": _model(),
        "input": text,
        "references": [{"audio": _ref_uri(Path(profile["ref_path"])), "text": prompt_text or "你好。"}],
        "response_format": "mp3",
        "sample_rate": 32000,
        "speed": float(os.getenv("VOICE_CLONE_SPEED", "1.0") or 1.0),
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("VOICE_CLONE_TIMEOUT", "60") or 60)) as client:
            response = await client.post(
                f"{_base()}/audio/speech",
                headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code != 200:
            detail = response.text[:160].replace("\n", " ")
            logger.warning(f"[TTS] 克隆服务返回 {response.status_code}：{detail}")
            return False
        target.write_bytes(response.content)
        return target.stat().st_size > 1024
    except Exception as exc:
        logger.warning(f"[TTS] 克隆合成失败：{type(exc).__name__}")
        return False


def _http_payload(text: str, profile: dict[str, str]) -> dict[str, object]:
    """自建 GPT-SoVITS v2 的参数；换别的服务只改这里。"""
    return {
        "text": text,
        "text_lang": os.getenv("VOICE_CLONE_LANG", "zh"),
        "ref_audio_path": profile["ref_path"],
        "prompt_text": profile.get("prompt_text", ""),
        "prompt_lang": "zh",
        "media_type": "wav",
        "streaming_mode": False,
    }


async def _http_tts(text: str, profile: dict[str, str], target: Path) -> bool:
    import httpx

    url = os.getenv("VOICE_CLONE_URL", "").strip()
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("VOICE_CLONE_TIMEOUT", "60") or 60)) as client:
            response = await client.post(url, json=_http_payload(text, profile))
        if response.status_code != 200:
            logger.warning(f"[TTS] 克隆服务返回 {response.status_code}")
            return False
        if "json" in response.headers.get("content-type", ""):
            payload = response.json()
            encoded = payload.get("data") or payload.get("audio") or ""
            if not encoded:
                logger.warning("[TTS] 克隆服务没给音频")
                return False
            target.write_bytes(base64.b64decode(encoded))
        else:
            target.write_bytes(response.content)
        return target.stat().st_size > 1024
    except Exception as exc:
        logger.warning(f"[TTS] 克隆合成失败：{type(exc).__name__}")
        return False
