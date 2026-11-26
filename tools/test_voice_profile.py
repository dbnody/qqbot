"""回归检查：音色样本能存能删，克隆可用时优先走克隆，没配置时回落到普通语音。

运行：python tools/test_voice_profile.py
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

TMP = Path(tempfile.mkdtemp(prefix="voice-test-"))
os.environ["QQBOT_DATABASE_PATH"] = str(TMP / "test.db")

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter, Message, MessageSegment  # noqa: E402
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent, Sender  # noqa: E402
from nonebot.exception import FinishedException  # noqa: E402

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)

from app import clone_tts, tts, voice_profile  # noqa: E402
from app.database import init_database  # noqa: E402

plugin = importlib.import_module("plugins.voice_custom")

voice_profile.VOICE_DIR = TMP / "voices"
SCOPE = "private:50001"
SAMPLE = b"RIFF" + b"\0" * 8000  # 够长就行，测试不看内容


def make_wav(name: str = "sample.wav") -> Path:
    path = TMP / name
    path.write_bytes(SAMPLE)
    return path


class FakeArgs:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def extract_plain_text(self) -> str:
        return self.text


def private_event(message: Message) -> PrivateMessageEvent:
    return PrivateMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="friend",
        user_id=50001,
        message_type="private",
        message_id=1,
        message=message,
        original_message=message,
        raw_message="",
        font=0,
        sender=Sender(user_id=50001, nickname="测试"),
        to_me=True,
        reply=None,
    )


def group_event() -> GroupMessageEvent:
    message = Message("x")
    return GroupMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="normal",
        user_id=50001,
        message_type="group",
        message_id=1,
        message=message,
        original_message=message,
        raw_message="x",
        font=0,
        sender=Sender(user_id=50001, nickname="测试", role="member"),
        to_me=True,
        group_id=900,
        reply=None,
    )


def run(event, text: str) -> str:
    sent: list[object] = []

    async def fake_send(message=None, *args, **kwargs):
        if message is not None:
            sent.append(message)

    async def fake_finish(message=None, *args, **kwargs):
        if message is not None:
            sent.append(message)
        raise FinishedException

    plugin.voice_cmd.send = fake_send
    plugin.voice_cmd.finish = fake_finish

    async def _go() -> None:
        try:
            await plugin.handle_voice_profile(event, FakeArgs(text))
        except FinishedException:
            pass

    asyncio.run(_go())
    parts = []
    for item in sent:
        if isinstance(item, Message):
            parts.append(item.extract_plain_text())
        elif isinstance(item, MessageSegment):
            parts.append(f"<{item.type}>")
        else:
            parts.append(str(item))
    return " ".join(parts)


def check_profile() -> None:
    assert voice_profile.get_profile(SCOPE) is None, "一开始不该有样本"
    path = voice_profile.save_sample(SCOPE, SAMPLE, ".wav")
    assert path.exists() and path.read_bytes() == SAMPLE, "样本应原样落盘"
    profile = voice_profile.get_profile(SCOPE)
    assert profile is not None and profile["ref_path"] == str(path)
    assert "已经录过" in voice_profile.describe(SCOPE)

    try:
        voice_profile.save_sample(SCOPE, b"tiny", ".wav")
    except ValueError:
        pass
    else:
        raise AssertionError("太短的音频应该被拒绝")

    assert voice_profile.clear(SCOPE) is True
    assert voice_profile.get_profile(SCOPE) is None, "清除后不该还有档案"
    assert "还没录过" in voice_profile.describe(SCOPE)


def check_clone_priority() -> None:
    voice_profile.save_sample(SCOPE, SAMPLE, ".wav")
    cloned = TMP / "cloned.wav"
    cloned.write_bytes(SAMPLE)
    originality = (clone_tts.synthesize_clone, tts._edge_tts)

    async def fake_clone(text, profile):
        return cloned

    async def fail_edge(*args, **kwargs):
        raise AssertionError("有克隆音色时不该再走 edge-tts")

    clone_tts.synthesize_clone = fake_clone
    tts._edge_tts = fail_edge
    try:
        got = asyncio.run(tts.synthesize("你好呀", None, SCOPE))
        assert got == cloned, f"应优先用克隆结果，实际 {got}"

        async def no_clone(text, profile):
            return None

        clone_tts.synthesize_clone = no_clone
        edge_file = TMP / "edge.mp3"
        edge_file.write_bytes(SAMPLE)

        async def fake_edge(text, voice, target):
            Path(target).write_bytes(SAMPLE)
            return True

        tts._edge_tts = fake_edge
        got = asyncio.run(tts.synthesize("你好呀", None, SCOPE))
        assert got is not None and got.exists(), "克隆不可用时应回落到 edge"
    finally:
        clone_tts.synthesize_clone, tts._edge_tts = originality
        voice_profile.clear(SCOPE)


def check_plugin() -> None:
    voice_profile.clear(SCOPE)
    wav = make_wav()
    record = MessageSegment.record(file=wav.resolve().as_uri())

    reply = run(group_event(), "录入")
    assert "私聊" in reply, f"群里应被拦住，实际：{reply}"

    reply = run(private_event(Message("x")), "状态")
    assert "还没录过" in reply, f"状态应显示未录入，实际：{reply}"

    reply = run(private_event(Message(record)), "录入")
    assert "存好了" in reply, f"录入应成功，实际：{reply}"
    assert voice_profile.get_profile(SCOPE) is not None, "录入后应有档案"

    reply = run(private_event(Message("x")), "状态")
    assert "已经录过" in reply, f"状态应显示已录入，实际：{reply}"

    reply = run(private_event(Message("x")), "清除")
    assert "删掉了" in reply, f"清除应成功，实际：{reply}"
    assert voice_profile.get_profile(SCOPE) is None


def check_hidden_from_help() -> None:
    help_text = (ROOT / "plugins" / "help" / "__init__.py").read_text(encoding="utf-8")
    assert "音色" not in help_text, "内测功能不该出现在帮助菜单"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "/音色" not in readme, "内测功能不该写进 README"


def main() -> None:
    init_database()
    check_profile()
    check_clone_priority()
    check_plugin()
    check_hidden_from_help()
    print("test_voice_profile passed")


if __name__ == "__main__":
    main()
