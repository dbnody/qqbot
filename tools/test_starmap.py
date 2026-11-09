"""回归检查：记忆星图按会话隔离、能出 PNG/GIF、/记忆星图 会发图片。

不连 QQ，用假的 matcher.send/finish 记录发出的消息。
运行：python tools/test_starmap.py
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

# 测试用独立数据库，别碰真实记忆。
TMP = Path(tempfile.mkdtemp(prefix="starmap-test-"))
os.environ["QQBOT_DATABASE_PATH"] = str(TMP / "test.db")

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter, Message, PrivateMessageEvent  # noqa: E402
from nonebot.adapters.onebot.v11.event import Sender  # noqa: E402
from nonebot.exception import FinishedException  # noqa: E402
from PIL import Image  # noqa: E402

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)

from app import starmap  # noqa: E402
from app.database import get_connection, init_database  # noqa: E402

GROUP = [
    "小胖喜欢喝冰美式",
    "小胖在杭州做后端",
    "小胖养了一只橘猫叫年糕",
]
PRIVATE = [
    "阿哲在准备面试",
    "阿哲喜欢兰州拉面",
]


def seed() -> None:
    init_database()
    with get_connection() as connection:
        for fact in GROUP:
            connection.execute("INSERT INTO ai_facts (scope_id, content) VALUES ('group:1001', ?)", (fact,))
        for fact in PRIVATE:
            connection.execute("INSERT INTO ai_facts (scope_id, content) VALUES ('private:2002', ?)", (fact,))
        connection.execute(
            "INSERT INTO ai_summaries (scope_id, summary, upto_id) VALUES ('group:1001', '群里的闲聊记录', 1)"
        )
        connection.execute(
            "INSERT INTO ai_summaries (scope_id, summary, upto_id) VALUES ('private:2002', '私聊里的近况', 1)"
        )


def check_load() -> None:
    facts, summaries, _ = starmap._load("group:1001")
    assert len(facts) == 3, f"应只取到本群的 3 条事实，实际 {len(facts)}"
    assert {item["scope_id"] for item in facts} == {"group:1001"}, "不能混入其它会话"
    assert "群里的闲聊记录" in summaries.values()
    facts, _, _ = starmap._load("private:2002")
    assert len(facts) == 2 and {item["scope_id"] for item in facts} == {"private:2002"}


def check_png() -> Path:
    path = starmap.render(TMP / "starmap.png", scope="group:1001")
    assert path is not None, "有事实时应出图"
    image = Image.open(path)
    assert image.size == (starmap.SIZE, starmap.SIZE), f"尺寸不对：{image.size}"
    assert image.mode == "RGB"
    assert path.stat().st_size > 20_000, "图片太小，可能没画上东西"
    return path


def check_gif() -> None:
    path = starmap.render(TMP / "starmap.png", gif=True, scope="group:1001")
    assert path is not None and path.suffix == ".png"
    gif = path.with_suffix(".gif")
    assert gif.exists(), "GIF 没生成"
    frames = Image.open(gif).n_frames
    assert frames == 8, f"应有 8 帧阶段动画，实际 {frames}"


def check_empty() -> None:
    assert starmap.render(TMP / "empty.png", scope="group:9999") is None, "没有事实时应返回 None"


def make_event() -> PrivateMessageEvent:
    message = Message("记忆星图")
    return PrivateMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="friend",
        user_id=2002,
        message_type="private",
        message_id=1,
        message=message,
        original_message=message,
        raw_message="记忆星图",
        font=0,
        sender=Sender(user_id=2002, nickname="测试"),
        to_me=True,
        reply=None,
    )


class FakeArgs:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def extract_plain_text(self) -> str:
        return self.text


async def check_handler() -> None:
    plugin = importlib.import_module("plugins.ai_persona")
    sent: list[Any] = []
    seen: dict[str, Any] = {}

    async def fake_send(message, *args, **kwargs):
        sent.append(message)
        return {"message_id": 1}

    async def fake_finish(message=None, *args, **kwargs):
        if message is not None:
            sent.append(message)
        raise FinishedException

    def spy(out=None, *, gif=False, scope=""):
        seen["scope"] = scope
        seen["gif"] = gif
        return TMP / "handler.png"

    original = plugin.starmap.render
    plugin.starmap_command.send = fake_send
    plugin.starmap_command.finish = fake_finish
    plugin.starmap.render = spy
    try:
        for text, want_gif in (("", False), ("过程", True)):
            sent.clear()
            try:
                await plugin.handle_starmap(make_event(), FakeArgs(text))
            except FinishedException:
                pass
            assert seen["scope"] == "private:2002", f"命令必须用当前会话，实际 {seen['scope']}"
            assert seen["gif"] is want_gif, f"gif 参数不对：{seen['gif']}"
            assert sent, "应当有回复"
            last = sent[-1]
            seg_type = last.type if hasattr(last, "type") else last[0].type
            assert seg_type == "image", f"最后一条应是图片，实际 {last}"
    finally:
        plugin.starmap.render = original


def main() -> None:
    seed()
    check_load()
    check_png()
    check_gif()
    check_empty()
    asyncio.run(check_handler())
    print("test_starmap passed")
    print("样张：", TMP)


if __name__ == "__main__":
    main()
