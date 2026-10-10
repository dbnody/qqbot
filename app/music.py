"""QQ 音乐和网易云音乐搜索服务。"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class SongResult:
    platform: str
    title: str
    artist: str
    song_id: int
    detail_url: str


def _first_artist(value: Any) -> str:
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("name") or first.get("title") or "未知歌手")
    return "未知歌手"


def _normalized(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.lower())


def _pick_song(items: list[dict[str, Any]], keyword: str, artist_key: str) -> dict[str, Any] | None:
    """从搜索候选中优先挑选歌名精确匹配、歌手匹配的结果。"""
    if not items:
        return None
    tokens = [_normalized(token) for token in keyword.split() if _normalized(token)]
    query = _normalized(keyword)

    def score(item: dict[str, Any]) -> int:
        title = _normalized(str(item.get("songname") or item.get("name") or ""))
        artist = _normalized(_first_artist(item.get(artist_key) or item.get("ar") or item.get("artists")))
        value = sum(2 for token in tokens if token in title) + sum(5 for token in tokens if token in artist)
        if title and any(title == token for token in tokens):
            value += 8
        if query and title == query:
            value += 10
        return value

    return max(enumerate(items), key=lambda pair: (score(pair[1]), -pair[0]))[1]


async def _search_qq(client: httpx.AsyncClient, keyword: str) -> SongResult | None:
    try:
        response = await client.get(
            "https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
            params={"w": keyword, "p": 1, "n": 10, "format": "json"},
            headers={"Referer": "https://y.qq.com/", "User-Agent": "qqbot-python/1.0"},
        )
        response.raise_for_status()
        song_list = response.json().get("data", {}).get("song", {}).get("list", [])
        if not song_list:
            return None
        item = _pick_song(song_list, keyword, "singer")
        if item is None:
            return None
        song_id = int(item.get("songid") or 0)
        if song_id <= 0:
            return None
        mid = str(item.get("songmid") or "")
        title = str(item.get("songname") or keyword)
        return SongResult("qq", title, _first_artist(item.get("singer")), song_id, f"https://y.qq.com/n/ryqq/songDetail/{mid}")
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def _search_netease(client: httpx.AsyncClient, keyword: str) -> SongResult | None:
    try:
        response = await client.get(
            "https://music.163.com/api/search/get/web",
            params={"s": keyword, "type": 1, "offset": 0, "limit": 10},
            headers={"Referer": "https://music.163.com/", "User-Agent": "qqbot-python/1.0"},
        )
        response.raise_for_status()
        song_list = response.json().get("result", {}).get("songs", [])
        if not song_list:
            return None
        item = _pick_song(song_list, keyword, "artists")
        if item is None:
            return None
        song_id = int(item.get("id") or 0)
        if song_id <= 0:
            return None
        return SongResult(
            "163",
            str(item.get("name") or keyword),
            _first_artist(item.get("artists") or item.get("ar")),
            song_id,
            f"https://music.163.com/#/song?id={song_id}",
        )
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return None


async def search_songs(keyword: str, platform: str = "both") -> list[SongResult]:
    """搜索歌曲，platform 可为 qq、163 或 both。"""
    keyword = keyword.strip()[:100]
    if not keyword:
        return []
    timeout = httpx.Timeout(8.0, connect=4.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        jobs = []
        if platform in {"qq", "both"}:
            jobs.append(_search_qq(client, keyword))
        if platform in {"163", "both"}:
            jobs.append(_search_netease(client, keyword))
        results = await asyncio.gather(*jobs, return_exceptions=False)
    return [result for result in results if result is not None]
