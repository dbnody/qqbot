"""QQ 头像临时下载工具。"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx


class AvatarError(RuntimeError):
    """头像下载失败。"""


async def download_avatar(user_id: str) -> Path:
    """下载 QQ 头像到临时文件，调用方必须在 finally 中删除。"""
    if not re.fullmatch(r"\d{5,12}", str(user_id)):
        raise AvatarError("QQ 号格式不正确")
    url = f"https://q1.qlogo.cn/g?b=qq&nk={int(user_id)}&s=640"
    temp_dir = Path("data") / "avatar_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(
        mode="wb", suffix=".jpg", prefix=f"avatar_{int(user_id)}_", dir=temp_dir, delete=False
    )
    output = Path(temp_file.name)
    total = 0
    try:
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "qqbot-python/1.0"}) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not content_type.startswith("image/"):
                    raise AvatarError("QQ 头像接口返回的不是图片")
                async for chunk in response.aiter_bytes(128 * 1024):
                    total += len(chunk)
                    if total > 5 * 1024 * 1024:
                        raise AvatarError("头像文件超过 5 MB 限制")
                    temp_file.write(chunk)
        temp_file.close()
        return output
    except AvatarError:
        temp_file.close()
        output.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        temp_file.close()
        output.unlink(missing_ok=True)
        raise AvatarError("头像下载失败，请稍后再试") from exc


async def download_image(source: str) -> tuple[Path, bool]:
    """准备一张待分析图片，返回路径和是否需要由调用方删除。"""
    source = unquote(str(source).strip())
    if source.startswith("file://"):
        source = urlparse(source).path
    local_path = Path(source)
    if local_path.exists() and local_path.is_file():
        if local_path.stat().st_size > 5 * 1024 * 1024:
            raise AvatarError("图片超过 5 MB 限制")
        return local_path, False
    if not source.lower().startswith(("http://", "https://")):
        raise AvatarError("无法读取这张图片")

    temp_dir = Path("data") / "avatar_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=".img", prefix="roast_", dir=temp_dir, delete=False)
    output = Path(temp_file.name)
    total = 0
    try:
        timeout = httpx.Timeout(15.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "qqbot-python/1.0"}) as client:
            async with client.stream("GET", source) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if content_type and not content_type.startswith("image/"):
                    raise AvatarError("链接内容不是图片")
                async for chunk in response.aiter_bytes(128 * 1024):
                    total += len(chunk)
                    if total > 5 * 1024 * 1024:
                        raise AvatarError("图片超过 5 MB 限制")
                    temp_file.write(chunk)
        temp_file.close()
        return output, True
    except AvatarError:
        temp_file.close()
        output.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        temp_file.close()
        output.unlink(missing_ok=True)
        raise AvatarError("图片下载失败，请稍后再试") from exc
