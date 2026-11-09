"""记忆星图：把事实库画成「圆环 → 连线 → 满天星」。

纯本地计算，不依赖 embedding：
- 相似度用中文 2-gram 的余弦，和 app/memory.py 的召回口径一致；
- 同一个 scope 的事实按时间排成圆环，摘要当圆心；
- 以圆环坐标为初值跑力导向，锚点逐渐松开，边把相似的事实拉在一起。

对外接口只有 render()：出 PNG，或按阶段拼成 GIF。
"""

from __future__ import annotations

import math
import os
import random
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.database import get_connection

SIZE = 1100
SS = 2  # 超采样倍数，先画大图再缩小，线条才不锯齿
PANEL = SIZE * SS
MAX_FACTS = 300
STEPS = 90
BG = (7, 10, 24)
PALETTE = [
    (126, 196, 255),
    (172, 146, 255),
    (255, 168, 200),
    (138, 255, 220),
    (255, 208, 138),
    (196, 214, 255),
]
_FONT_PATH = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc"


def _grams(text: str) -> set[str]:
    """中文按 2 字切块，英文/数字按词切块，够用且零依赖。"""
    lowered = str(text).lower()
    out = set(re.findall(r"[a-z0-9_]{2,}", lowered))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", lowered):
        out.update(chunk[i : i + 2] for i in range(len(chunk) - 1))
        if len(chunk) == 1:
            out.add(chunk)
    return out


def _cosine(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def _load(scope_filter: str = "") -> tuple[list[dict], dict[str, str], list[dict]]:
    facts_sql = "SELECT id, scope_id, content, created_at FROM ai_facts"
    args: tuple = ()
    if scope_filter:
        facts_sql += " WHERE scope_id = ?"
        args = (scope_filter,)
    with get_connection() as connection:
        facts = [dict(row) for row in connection.execute(facts_sql + " ORDER BY id", args)]
        summaries = {
            str(row["scope_id"]): str(row["summary"])
            for row in connection.execute("SELECT scope_id, summary FROM ai_summaries")
            if str(row["summary"]).strip()
        }
        memories = [
            dict(row)
            for row in connection.execute("SELECT scope_id, content FROM ai_memories ORDER BY id")
        ]
    return facts, summaries, memories


def _build_nodes(facts: list[dict], summaries: dict[str, str]) -> list[dict]:
    nodes: list[dict] = []
    for fact in facts[:MAX_FACTS]:
        content = str(fact["content"])
        nodes.append(
            {
                "key": f"f{fact['id']}",
                "scope_id": str(fact["scope_id"]),
                "content": content,
                "grams": _grams(content),
                "kind": "fact",
                "born": str(fact.get("created_at") or ""),
                "size": 2.4 + min(3.0, len(content) / 18),
            }
        )
    for scope in {node["scope_id"] for node in nodes}:
        text = summaries.get(scope, "")
        nodes.append(
            {
                "key": f"sum:{scope}",
                "scope_id": scope,
                "content": text or scope,
                "grams": _grams(text),
                "kind": "summary",
                "born": "",
                "size": 6.5,
            }
        )
    return nodes


def _build_edges(nodes: list[dict]) -> list[tuple[str, str, float]]:
    by_scope: dict[str, list[dict]] = {}
    for node in nodes:
        if node["kind"] == "fact":
            by_scope.setdefault(node["scope_id"], []).append(node)

    scores: dict[tuple[str, str], float] = {}
    for group in by_scope.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                left, right = group[i], group[j]
                score = _cosine(left["grams"], right["grams"])
                if left["born"] and left["born"] == right["born"]:
                    # 同一批压缩抽出来的事实，天然属于同一段对话。
                    score = min(1.0, score + 0.35)
                if score >= 0.18:
                    scores[(left["key"], right["key"])] = score

    # 每个点只留最强的 3 条边，否则会连成一团糊。
    ranked: dict[str, list[tuple[float, str]]] = {}
    for (left, right), score in scores.items():
        ranked.setdefault(left, []).append((score, right))
        ranked.setdefault(right, []).append((score, left))
    keep: set[tuple[str, str]] = set()
    for key, items in ranked.items():
        for _, other in sorted(items, reverse=True)[:3]:
            keep.add((key, other) if key < other else (other, key))

    edges = [(left, right, scores.get((left, right), 0.2)) for left, right in keep]
    for node in nodes:
        if node["kind"] == "summary":
            for fact in by_scope.get(node["scope_id"], []):
                edges.append((node["key"], fact["key"], 0.12))
    return edges


def _seeds(nodes: list[dict]) -> dict[str, tuple[float, float]]:
    scopes: dict[str, int] = {}
    for node in nodes:
        if node["kind"] == "fact":
            scopes[node["scope_id"]] = scopes.get(node["scope_id"], 0) + 1
    order = sorted(scopes, key=lambda name: scopes[name], reverse=True)
    radius = 235.0 if len(order) > 1 else 0.0
    origin = PANEL / 2
    centers: dict[str, tuple[float, float]] = {}
    for index, scope in enumerate(order):
        angle = 2 * math.pi * index / max(1, len(order))
        centers[scope] = (
            origin + math.cos(angle) * radius,
            origin + math.sin(angle) * radius,
        )

    counts: dict[str, int] = {scope: 0 for scope in order}
    pos: dict[str, tuple[float, float]] = {}
    for node in nodes:
        if node["kind"] == "summary":
            pos[node["key"]] = centers[node["scope_id"]]
    for node in nodes:
        if node["kind"] != "fact":
            continue
        scope = node["scope_id"]
        total = max(1, scopes.get(scope, 1))
        index = counts[scope]
        counts[scope] += 1
        ring = 105.0 + 13.0 * math.sqrt(total)
        angle = 2 * math.pi * index / total - math.pi / 2
        cx, cy = centers[scope]
        pos[node["key"]] = (cx + math.cos(angle) * ring, cy + math.sin(angle) * ring)
    return pos


def _layout(
    pos: dict[str, tuple[float, float]],
    edges: list[tuple[str, str, float]],
) -> dict[str, tuple[float, float]]:
    keys = list(pos)
    index = {key: i for i, key in enumerate(keys)}
    points = np.array([pos[key] for key in keys], dtype=float)
    anchors = points.copy()
    springs = np.array(
        [
            (index[left], index[right], weight)
            for left, right, weight in edges
            if left in index and right in index
        ],
        dtype=float,
    )

    heat = 34.0
    center = PANEL / 2
    for step in range(STEPS):
        delta = points[:, None, :] - points[None, :, :]
        distance = np.sqrt((delta**2).sum(-1)) + 1e-6
        force = (delta / (distance[..., None] ** 2)).sum(1) * 520.0

        if len(springs):
            left = springs[:, 0].astype(int)
            right = springs[:, 1].astype(int)
            weight = springs[:, 2]
            vector = points[right] - points[left]
            length = np.sqrt((vector**2).sum(-1))[:, None] + 1e-6
            pull = vector / length * (length - 120.0) * (weight * 0.4)[:, None]
            np.add.at(force, left, pull)
            np.add.at(force, right, -pull)

        # 锚点越到后面越松，圆环结构才会逐步散成星云。
        force += (anchors - points) * 0.012 * (1 - step / STEPS)
        # 一点向心力，防止星团被斥力推出画布。
        force += (center - points) * 0.009
        norm = np.sqrt((force**2).sum(-1))[:, None] + 1e-6
        points += force / norm * np.minimum(norm, heat)
        points = np.clip(points, 130, PANEL - 130)
        heat = max(3.5, heat * 0.955)

    return {key: (float(points[index[key]][0]), float(points[index[key]][1])) for key in keys}


def _fit(pos: dict[str, tuple[float, float]], ratio: float = 0.36) -> dict[str, tuple[float, float]]:
    """把最终布局缩放到画面内，稀疏数据也能铺满，密集数据不会出界。"""
    if not pos:
        return pos
    xs = [x for x, _ in pos.values()]
    ys = [y for _, y in pos.values()]
    center = PANEL / 2
    extent = max(max(xs) - min(xs), max(ys) - min(ys)) / 2 or 1.0
    scale = min(4.0, (PANEL * ratio) / extent)
    return {
        key: (center + (x - center) * scale, center + (y - center) * scale)
        for key, (x, y) in pos.items()
    }


def _font(size: int) -> ImageFont.FreeTypeFont | None:
    if not _FONT_PATH.exists():
        return None
    try:
        return ImageFont.truetype(str(_FONT_PATH), size)
    except OSError:
        return None


def _colors(nodes: list[dict]) -> dict[str, tuple[int, int, int]]:
    """按 scope 首次出现顺序稳定配色，同一张图里每个群/私聊颜色固定。"""
    scopes = sorted({node["scope_id"] for node in nodes})
    return {scope: PALETTE[index % len(PALETTE)] for index, scope in enumerate(scopes)}


def _dust(count: int = 420, seed: int = 7) -> list[tuple[float, float, int]]:
    rng = random.Random(seed)
    half = PANEL / 2
    stars = []
    for _ in range(count):
        angle = rng.random() * math.tau
        distance = math.sqrt(rng.random()) * half * 0.98
        stars.append(
            (
                half + math.cos(angle) * distance,
                half + math.sin(angle) * distance,
                rng.randint(18, 70),
            )
        )
    return stars


def _draw(
    pos: dict[str, tuple[float, float]],
    nodes: list[dict],
    edges: list[tuple[str, str, float]],
    edge_alpha: float,
    labels: bool,
    degree: dict[str, int],
    colors: dict[str, tuple[int, int, int]],
) -> Image.Image:
    half = PANEL / 2
    canvas = Image.new("RGBA", (PANEL, PANEL), (*BG, 255))

    # 背景：淡蓝星云 + 固定星尘，每帧底图一致，动画才不会闪。
    nebula = Image.new("RGBA", (PANEL, PANEL), (0, 0, 0, 0))
    ImageDraw.Draw(nebula).ellipse(
        (half - half * 0.72, half - half * 0.72, half + half * 0.72, half + half * 0.72),
        fill=(38, 62, 120, 46),
    )
    canvas = Image.alpha_composite(canvas, nebula.filter(ImageFilter.GaussianBlur(120 * SS)))
    draw = ImageDraw.Draw(canvas)
    for x, y, bright in _dust():
        r = 1.0 * SS if bright > 45 else 0.7 * SS
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(bright + 40, bright + 55, bright + 80))

    if edges and edge_alpha > 0:
        lines = Image.new("RGBA", (PANEL, PANEL), (0, 0, 0, 0))
        line_draw = ImageDraw.Draw(lines)
        for left, right, weight in edges:
            if left not in pos or right not in pos:
                continue
            alpha = int(min(150, 40 + weight * 160) * edge_alpha)
            line_draw.line((*pos[left], *pos[right]), fill=(120, 168, 235, alpha), width=SS)
        canvas = Image.alpha_composite(canvas, lines.filter(ImageFilter.GaussianBlur(0.8 * SS)))

    glow = Image.new("RGBA", (PANEL, PANEL), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for node in nodes:
        x, y = pos[node["key"]]
        radius = node["size"] * SS
        hue = colors[node["scope_id"]]
        glow_draw.ellipse((x - radius * 3, y - radius * 3, x + radius * 3, y + radius * 3), fill=(*hue, 52))
    canvas = Image.alpha_composite(canvas, glow.filter(ImageFilter.GaussianBlur(7 * SS)))

    core = ImageDraw.Draw(canvas)
    for node in nodes:
        x, y = pos[node["key"]]
        radius = node["size"] * SS
        hue = colors[node["scope_id"]]
        if node["kind"] == "summary":
            for arm, alpha in ((radius * 3.2, 90), (radius * 2.0, 130), (radius * 1.2, 200)):
                core.line((x - arm, y, x + arm, y), fill=(*hue, alpha), width=max(1, SS // 2))
                core.line((x, y - arm, x, y + arm), fill=(*hue, alpha), width=max(1, SS // 2))
        core.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*hue, 235))
        core.ellipse((x - radius * 0.45, y - radius * 0.45, x + radius * 0.45, y + radius * 0.45), fill=(255, 255, 255, 230))

    if labels:
        font = _font(int(13 * SS))
        head = _font(int(16 * SS))
        if font and head:
            top = sorted(
                (node for node in nodes if node["kind"] == "fact"),
                key=lambda node: degree.get(node["key"], 0),
                reverse=True,
            )[:6]
            taken: list[tuple[float, float, float, float]] = []
            order = [n for n in nodes if n["kind"] == "summary"] + top
            for node in order:
                x, y = pos[node["key"]]
                text = str(node["content"]).replace("\n", " ")
                limit = 13 if node["kind"] == "summary" else 9
                text = text if len(text) <= limit else text[: limit - 1] + "…"
                draw_font = head if node["kind"] == "summary" else font
                left, top_edge, right, bottom = draw_font.getbbox(text)
                width, height = right - left, bottom - top_edge
                gap = node["size"] * SS + 5 * SS
                base_y = y - 7 * SS
                candidates = [
                    (x + gap, base_y),
                    (x - gap - width, base_y),
                    (x - width / 2, base_y - height - gap * 0.8),
                    (x - width / 2, base_y + height + gap * 0.6),
                ]
                for anchor_x, anchor_y in candidates:
                    box = (anchor_x - 3, anchor_y + top_edge - 3, anchor_x + width + 3, anchor_y + bottom + 3)
                    if box[0] < 6 or box[2] > PANEL - 6 or box[1] < 6 or box[3] > PANEL - 6:
                        continue
                    if any(
                        box[0] < other[2] and other[0] < box[2] and box[1] < other[3] and other[1] < box[3]
                        for other in taken
                    ):
                        continue
                    taken.append(box)
                    core.text((anchor_x + SS, anchor_y + SS), text, font=draw_font, fill=(0, 0, 0, 200))
                    core.text((anchor_x, anchor_y), text, font=draw_font, fill=(232, 240, 255, 235))
                    break

    return canvas.resize((SIZE, SIZE), Image.LANCZOS).convert("RGB")


def render(
    out: str | Path | None = None,
    *,
    gif: bool = False,
    scope: str = "",
) -> Path | None:
    """画一张记忆星图；没有事实时返回 None。"""
    facts, summaries, memories = _load(scope)
    if not facts:
        return None
    nodes = _build_nodes(facts, summaries)
    edges = _build_edges(nodes)
    degree: dict[str, int] = {}
    for left, right, _ in edges:
        degree[left] = degree.get(left, 0) + 1
        degree[right] = degree.get(right, 0) + 1
    _ = memories  # 星尘数量暂时固定，留个位置以后按记忆量调节
    colors = _colors(nodes)

    seeds = _seeds(nodes)
    final = _fit(_layout(seeds, edges))

    target = Path(out) if out else Path("data/starmap/memory_star.png")
    if target.suffix.lower() != ".png":
        target = target.with_suffix(".png")
    target.parent.mkdir(parents=True, exist_ok=True)

    final_image = _draw(final, nodes, edges, 1.0, labels=True, degree=degree, colors=colors)
    final_image.save(target)

    if not gif:
        return target

    frames = []
    for index, alpha in enumerate((0.0, 0.18, 0.34, 0.5, 0.66, 0.8, 0.9, 1.0)):
        blend = max(0.0, min(1.0, (alpha - 0.18) / 0.82))
        pos = {
            key: (
                seeds[key][0] + (final[key][0] - seeds[key][0]) * blend,
                seeds[key][1] + (final[key][1] - seeds[key][1]) * blend,
            )
            for key in seeds
        }
        image = _draw(pos, nodes, edges, alpha, labels=index == 7, degree=degree, colors=colors)
        frames.append(image.resize((700, 700), Image.LANCZOS).convert("P", palette=Image.ADAPTIVE, colors=192))
    gif_target = target.with_suffix(".gif")
    frames[0].save(gif_target, save_all=True, append_images=frames[1:], duration=260, loop=0, optimize=True)
    return target
