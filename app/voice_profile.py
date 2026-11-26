"""音色档案：保存用户录入的参考音频（和它对应的文字），给克隆 TTS 用。

一个会话一份，重新录入就覆盖；文件放 data/voices/<scope 哈希>/，
数据库 ai_voices 只记元信息。参考音频统一压成 16k 单声道、最多 20 秒，
这样 base64 进请求体不会太大。
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.database import get_connection


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VOICE_DIR = PROJECT_ROOT / "data" / "voices"

MIN_BYTES = 4096  # 太短的音频克隆出来是杂音
MAX_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 20


def _folder(scope_id: str) -> Path:
    key = hashlib.sha1(str(scope_id).encode()).hexdigest()[:16]
    path = VOICE_DIR / key
    path.mkdir(parents=True, exist_ok=True)
    return path


def _to_wav(raw: bytes, suffix: str) -> Path:
    """统一成 16k 单声道 wav；没装 ffmpeg 就保留原文件。"""
    suffix = suffix if suffix.startswith(".") else f".{suffix}"
    temp_dir = Path(tempfile.mkdtemp(prefix="voice-ref-"))
    source = temp_dir / f"input{suffix}"
    source.write_bytes(raw)
    if suffix != ".wav" and shutil.which("ffmpeg") is None:
        return source
    if shutil.which("ffmpeg") is None:
        return source
    target = temp_dir / "input.wav"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
                "-ac", "1", "-ar", "16000", "-t", str(MAX_SECONDS), str(target),
            ],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.SubprocessError, OSError):
        return source
    return target if target.exists() and target.stat().st_size > MIN_BYTES else source


def save_sample(scope_id: str, raw: bytes, suffix: str = ".wav", prompt_text: str = "") -> Path:
    """存一份新的音色样本，返回落盘的 wav 路径。"""
    if len(raw) < MIN_BYTES:
        raise ValueError("音频太短，录 5 秒以上再试")
    if len(raw) > MAX_BYTES:
        raise ValueError("音频太大，30 秒以内就行")

    source = _to_wav(raw, suffix)
    folder = _folder(scope_id)
    for old in folder.iterdir():
        old.unlink(missing_ok=True)
    target = folder / "ref.wav"
    shutil.copyfile(source, target)
    shutil.rmtree(source.parent, ignore_errors=True)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_voices (scope_id, ref_path, prompt_text, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET ref_path = excluded.ref_path,
                prompt_text = excluded.prompt_text, updated_at = CURRENT_TIMESTAMP
            """,
            (str(scope_id), str(target), prompt_text.strip()),
        )
    return target


def set_transcript(scope_id: str, text: str) -> bool:
    """补/改参考音频对应的文字，文字对得上克隆才像。"""
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE ai_voices SET prompt_text = ?, updated_at = CURRENT_TIMESTAMP WHERE scope_id = ?",
            (text.strip(), str(scope_id)),
        )
        return cursor.rowcount > 0


def get_profile(scope_id: str) -> dict[str, str] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT scope_id, ref_path, prompt_text, engine FROM ai_voices WHERE scope_id = ?",
            (str(scope_id),),
        ).fetchone()
    if row is None:
        return None
    profile = {key: str(row[key]) for key in row.keys()}
    if not Path(profile["ref_path"]).exists():
        return None
    return profile


def clear(scope_id: str) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM ai_voices WHERE scope_id = ?", (str(scope_id),))
        removed = cursor.rowcount > 0
    folder = _folder(scope_id)
    for old in folder.iterdir():
        old.unlink(missing_ok=True)
    return removed


def describe(scope_id: str) -> str:
    profile = get_profile(scope_id)
    if profile is None:
        return "还没录过音色，用的默认声音。"
    size = Path(profile["ref_path"]).stat().st_size // 1024
    transcript = (profile.get("prompt_text") or "").strip()
    tail = f"参考文字：{transcript[:24]}…" if transcript else "参考文字缺了，用 /音色 文本 <原话> 补一下会更像。"
    return f"已经录过音色样本（{size}KB）。{tail}"
