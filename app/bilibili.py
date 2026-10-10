"""B 站公开视频解析和下载。

只接受 bilibili.com / b23.tv 链接，使用 B 站公开接口获取 360P MP4 流，
下载到本地后交给 OneBot 发送。默认限制 50 MB，可用环境变量调整。
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx


class BilibiliError(RuntimeError):
    """B 站解析或下载失败。"""


@dataclass(frozen=True)
class BilibiliVideo:
    bvid: str
    cid: int
    title: str
    duration: int
    size: int
    url: str


_BVID_RE = re.compile(r"\b(BV[0-9A-Za-z]{10})\b", re.I)
_AV_RE = re.compile(r"\bav(\d+)\b", re.I)
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/",
}


def max_video_bytes() -> int:
    try:
        return max(5, min(int(os.getenv("BILIBILI_MAX_MB", "50")), 200)) * 1024 * 1024
    except ValueError:
        return 50 * 1024 * 1024


def max_video_seconds() -> int:
    try:
        return max(30, min(int(os.getenv("BILIBILI_MAX_SECONDS", "600")), 3600))
    except ValueError:
        return 600


def _extract_from_url(value: str) -> tuple[str, str] | None:
    bvid = _BVID_RE.search(value)
    if bvid:
        raw_bvid = bvid.group(1)
        # BV 号区分大小写，只规范化前缀，不能对整个 ID 调用 upper()。
        return "bvid", "BV" + raw_bvid[2:]
    avid = _AV_RE.search(value)
    if avid:
        return "aid", avid.group(1)
    return None


async def extract_video_ref(text: str, client: httpx.AsyncClient) -> tuple[str, str] | None:
    """从消息中提取 BV/AV视频标识；b23.tv 短链会跟随重定向。"""
    direct = _extract_from_url(text)
    if direct:
        return direct
    short_urls = re.findall(r"https?://b23\.tv/[A-Za-z0-9]+", text, flags=re.I)
    for short_url in short_urls[:1]:
        try:
            response = await client.get(short_url, follow_redirects=True, headers=_HEADERS)
            direct = _extract_from_url(str(response.url))
            if direct:
                return direct
        except httpx.HTTPError:
            continue
    return None


async def fetch_video(text: str) -> BilibiliVideo | None:
    timeout = httpx.Timeout(12.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS) as client:
        reference = await extract_video_ref(text, client)
        if reference is None:
            return None
        kind, value = reference
        view_params = {"bvid": value} if kind == "bvid" else {"aid": value}
        try:
            view_response = await client.get("https://api.bilibili.com/x/web-interface/view", params=view_params)
            view_response.raise_for_status()
            view_payload = view_response.json()
            if view_payload.get("code") != 0:
                raise BilibiliError(str(view_payload.get("message") or "视频不存在或不可访问"))
            data = view_payload["data"]
            pages = data.get("pages") or []
            if not pages:
                raise BilibiliError("没有找到视频分 P 信息")
            page = 1
            match = re.search(r"[?&]p=(\d+)", text)
            if match:
                page = max(1, min(int(match.group(1)), len(pages)))
            selected = pages[page - 1]
            cid = int(selected["cid"])
            play_params = {
                ("bvid" if kind == "bvid" else "avid"): value,
                "cid": cid,
                "qn": 16,
                "fnval": 0,
                "fnver": 0,
                "fourk": 0,
            }
            play_response = await client.get("https://api.bilibili.com/x/player/playurl", params=play_params)
            play_response.raise_for_status()
            play_payload = play_response.json()
            if play_payload.get("code") != 0:
                raise BilibiliError(str(play_payload.get("message") or "无法获取视频流"))
            streams = play_payload.get("data", {}).get("durl") or []
            if not streams:
                raise BilibiliError("该视频没有可发送的 MP4 视频流")
            stream = streams[0]
            size = int(stream.get("size") or 0)
            duration = int(data.get("duration") or 0)
            if size > max_video_bytes():
                raise BilibiliError(f"视频文件约 {size / 1024 / 1024:.1f} MB，超过当前 {max_video_bytes() / 1024 / 1024:.0f} MB 限制")
            if duration > max_video_seconds():
                raise BilibiliError(f"视频时长约 {duration // 60} 分钟，超过当前 {max_video_seconds() // 60} 分钟限制")
            return BilibiliVideo(
                bvid=str(data.get("bvid") or value),
                cid=cid,
                title=str(data.get("title") or "B站视频").strip(),
                duration=duration,
                size=size,
                url=str(stream["url"]),
            )
        except BilibiliError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise BilibiliError("B站接口暂时不可用，请稍后再试") from exc


def _safe_filename(title: str) -> str:
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title).strip(" .")
    return (title or "bilibili_video")[:80]


async def download_video(video: BilibiliVideo) -> Path:
    output_dir = Path("data") / "bilibili"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"{_safe_filename(video.title)}_{video.bvid}_{stamp}.mp4"
    partial = output.with_suffix(".part")
    total = 0
    try:
        timeout = httpx.Timeout(60.0, connect=8.0)
        async with httpx.AsyncClient(timeout=timeout, headers=_HEADERS, follow_redirects=True) as client:
            async with client.stream("GET", video.url) as response:
                response.raise_for_status()
                content_length = int(response.headers.get("content-length") or 0)
                if content_length > max_video_bytes():
                    raise BilibiliError("视频文件超过发送大小限制")
                with partial.open("wb") as file:
                    async for chunk in response.aiter_bytes(1024 * 256):
                        total += len(chunk)
                        if total > max_video_bytes():
                            raise BilibiliError("下载中的视频超过发送大小限制")
                        file.write(chunk)
        partial.replace(output)
        return output
    except BilibiliError:
        partial.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, OSError) as exc:
        partial.unlink(missing_ok=True)
        raise BilibiliError("视频下载失败，请检查网络后重试") from exc
