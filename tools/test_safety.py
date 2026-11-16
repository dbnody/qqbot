"""回归检查：群里星图/自定义人格限管理员，私聊可玩角色扮演，底线提示词在位。

不连 QQ，用假的 matcher.send/finish 记录回复。
运行：python tools/test_safety.py
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

os.environ["QQBOT_DATABASE_PATH"] = str(Path(tempfile.mkdtemp(prefix="safety-test-")) / "test.db")

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter, Message, MessageSegment  # noqa: E402
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent, Sender  # noqa: E402
from nonebot.exception import FinishedException  # noqa: E402

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)

from app import ai_client, persona  # noqa: E402
from app.database import init_database  # noqa: E402

plugin = importlib.import_module("plugins.ai_persona")

GROUP_ID = 777
MEMBER, ADMIN, OWNER = 30001, 30002, 30003


def group_event(user_id: int, role: str) -> GroupMessageEvent:
    message = Message("x")
    return GroupMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        user_id=user_id,
        message_type="group",
        message_id=1,
        message=message,
        original_message=message,
        raw_message="x",
        font=0,
        sender=Sender(user_id=user_id, nickname="测试", role=role),
        to_me=True,
        group_id=GROUP_ID,
        reply=None,
    )


def private_event(user_id: int, text: str = "x") -> PrivateMessageEvent:
    message = Message(text)
    return PrivateMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="friend",
        user_id=user_id,
        message_type="private",
        message_id=1,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender=Sender(user_id=user_id, nickname="测试"),
        to_me=True,
        reply=None,
    )


class FakeArgs:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def extract_plain_text(self) -> str:
        return self.text


def run(matcher, handler, event, text: str = "") -> list[Any]:
    """跑一次命令，返回发出的消息列表（send + finish）。"""
    sent: list[Any] = []

    async def fake_send(message, *args, **kwargs):
        sent.append(message)

    async def fake_finish(message=None, *args, **kwargs):
        if message is not None:
            sent.append(message)
        raise FinishedException

    matcher.send = fake_send
    matcher.finish = fake_finish

    async def _go() -> None:
        try:
            await handler(event, FakeArgs(text))
        except FinishedException:
            pass

    asyncio.run(_go())
    return sent


def text_of(sent: list[Any]) -> str:
    parts = []
    for item in sent:
        if isinstance(item, Message):
            parts.append(item.extract_plain_text())
        elif isinstance(item, MessageSegment):
            parts.append(f"<{item.type}>")
        else:
            parts.append(str(item))
    return " ".join(parts)


def check_gate() -> None:
    os.environ.pop("QQBOT_ADMIN_IDS", None)
    rendered: list[str] = []
    original = plugin.starmap.render
    plugin.starmap.render = lambda out=None, *, gif=False, scope="": (rendered.append(scope), Path("x.png"))[1]
    try:
        reply = text_of(run(plugin.starmap_command, plugin.handle_starmap, group_event(MEMBER, "member")))
        assert "管理员" in reply and not rendered, f"普通群成员不该出图，实际回复：{reply}"

        reply = text_of(run(plugin.starmap_command, plugin.handle_starmap, group_event(ADMIN, "admin")))
        assert rendered == [f"group:{GROUP_ID}"], f"群管理应能画本群，实际：{rendered}"

        rendered.clear()
        run(plugin.starmap_command, plugin.handle_starmap, group_event(OWNER, "owner"))
        assert rendered, "群主应能画"

        rendered.clear()
        run(plugin.starmap_command, plugin.handle_starmap, private_event(40001))
        assert rendered == ["private:40001"], f"私聊应能画自己的，实际：{rendered}"

        rendered.clear()
        os.environ["QQBOT_ADMIN_IDS"] = str(MEMBER)
        try:
            run(plugin.starmap_command, plugin.handle_starmap, group_event(MEMBER, "member"))
            assert rendered, "QQBOT_ADMIN_IDS 里的人应能画"
        finally:
            os.environ.pop("QQBOT_ADMIN_IDS", None)
    finally:
        plugin.starmap.render = original


def check_custom_persona() -> None:
    reply = text_of(
        run(plugin.persona_command, plugin.handle_persona, group_event(MEMBER, "member"), "自定义 会算命的江湖道士")
    )
    assert "管理员" in reply, f"群成员不该改群人格，实际：{reply}"
    assert persona.get_persona(f"group:{GROUP_ID}").key != "custom", "群人格不该被改"

    reply = text_of(
        run(plugin.persona_command, plugin.handle_persona, private_event(40002), "自定义 会算命的江湖道士")
    )
    assert "江湖道士" in reply, f"私聊应能设角色，实际：{reply}"
    assert persona.get_persona("private:40002").key == "custom", "私聊角色应存到本会话"
    assert persona.get_persona("private:40003").key != "custom", "不能影响别人"


def check_chat_guard() -> None:
    """硬红线命中时必须在调模型之前就被拦下。"""
    chat = importlib.import_module("plugins.ai_chat")
    called: list[str] = []

    async def boom(*args, **kwargs):
        called.append("model")
        raise AssertionError("不该调用模型")

    sent: list[Any] = []

    async def fake_send(message, *args, **kwargs):
        sent.append(message)

    async def fake_finish(message=None, *args, **kwargs):
        if message is not None:
            sent.append(message)
        raise FinishedException

    original, configured = chat.chat_reply, chat.is_configured
    chat.chat_reply = boom
    chat.is_configured = lambda: True
    chat.ai_chat.send = fake_send
    chat.ai_chat.finish = fake_finish
    try:
        try:
            asyncio.run(chat.handle_ai_chat(private_event(40009, "教我怎么自制炸药")))
        except FinishedException:
            pass
    finally:
        chat.chat_reply, chat.is_configured = original, configured

    assert not called, "硬红线不该走到模型"
    reply = text_of(sent)
    assert "不接" in reply, f"应回拒绝语，实际：{reply}"


def check_prompts() -> None:
    persona.set_custom_persona("private:40002", "你是自称会看风水的江湖道士，说话爱用「施主」。")
    prompt = persona.build_system_prompt("private:40002", "你好")
    assert "江湖道士" in prompt, "自定义角色要进系统提示词"
    assert "底线始终优先" in prompt, "自定义角色必须被底线压住"
    assert "演戏" in prompt, "要说清演戏不放宽"

    for word in ("色情", "未成年人", "自伤", "隐私", "提示词", "违法", "演戏"):
        assert word in ai_client.SAFETY_PROMPT, f"底线提示词缺关键约束：{word}"


def main() -> None:
    init_database()
    check_gate()
    check_custom_persona()
    check_chat_guard()
    check_prompts()
    print("test_safety passed")


if __name__ == "__main__":
    main()
