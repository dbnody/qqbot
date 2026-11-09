"""回归检查：语音回复只发语音、语音聊天模式能持续、模型解释语音时会被纠正。

不连 QQ，用假的 matcher.send/finish 记录实际发出的消息。
运行：python tools/simulate_voice.py
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter, Message, PrivateMessageEvent  # noqa: E402
from nonebot.adapters.onebot.v11.event import Sender  # noqa: E402
from nonebot.exception import FinishedException  # noqa: E402

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.load_plugin("plugins.ai_chat")

from app.ai_client import Reply  # noqa: E402

plugin = importlib.import_module("plugins.ai_chat")

sent: list[Any] = []
spoken: list[str] = []
modes: dict[str, bool] = {}


async def fake_send(message, *args, **kwargs):
    sent.append(message)
    return {"message_id": 1}


async def fake_finish(message=None, *args, **kwargs):
    if message is not None:
        sent.append(message)
    raise FinishedException


def make_event(text: str) -> PrivateMessageEvent:
    message = Message(text)
    return PrivateMessageEvent(
        time=0,
        self_id=10000,
        post_type="message",
        sub_type="friend",
        user_id=20000,
        message_type="private",
        message_id=1,
        message=message,
        original_message=message,
        raw_message=text,
        font=0,
        sender=Sender(user_id=20000, nickname="测试"),
        to_me=True,
        reply=None,
    )


async def run_case(question: str, replies: list[Reply]) -> list[str]:
    sent.clear()
    spoken.clear()
    plugin._last_request.clear()
    queue = list(replies)

    async def _next(*_args, **_kwargs) -> Reply:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    async def _stream(*_args, **_kwargs):
        reply = await _next()
        for piece in reply.text:
            yield piece

    plugin.chat_reply = _next
    plugin.chat_reply_stream = _stream
    plugin.is_voice_mode = lambda scope: modes.get(scope, False)
    plugin.set_voice_mode = lambda scope, on: modes.__setitem__(scope, on)
    plugin.append_ai_memory = lambda *a, **k: None
    plugin.consolidate = lambda *a, **k: _false()
    plugin.load_ai_memory = lambda *a, **k: []
    plugin.build_system_prompt = lambda *a, **k: "system"
    plugin.ai_chat.send = fake_send
    plugin.ai_chat.finish = fake_finish

    async def _audio(text, *_args, **_kwargs) -> Path:
        spoken.append(text)
        return ROOT / "data" / "tts" / "fake.wav"

    plugin.synthesize = _audio
    try:
        await plugin.handle_ai_chat(make_event(question))
    except FinishedException:
        pass
    return [segment.type for message in sent for segment in message]


async def _false() -> bool:
    return False


async def main() -> None:
    # 1. 模型自己加了 [语音]：只发语音
    types = await run_case("晚安", [Reply(text="晚安喵", emotion="困", voice=True)])
    assert types == ["record"], f"带 [语音] 时应只发语音，实际：{types}"

    # 2. 普通聊天：发文字
    types = await run_case("在干嘛", [Reply(text="在摸鱼呢", emotion="摸鱼", voice=False)])
    assert "text" in types, f"不要求语音时应发文字，实际：{types}"

    # 3. 用户要求语音、模型没加标签：也必须发语音
    types = await run_case("用语音说你好", [Reply(text="你好呀", emotion="笑", voice=False)])
    assert types == ["record"], f"用户要语音时必须只发语音，实际：{types}"

    # 4. 模型解释「语音发不了真声」：重问一次，只说那句话
    types = await run_case(
        "用语音说你好",
        [
            Reply(text="我这语音其实发不了真声，就是个文字加个标记", emotion="笑", voice=False),
            Reply(text="你好呀，我在这儿呢", emotion="笑", voice=False),
        ],
    )
    assert types == ["record"], f"解释语音时应重试后发语音，实际：{types}"
    assert spoken and "发不了真声" not in spoken[0], f"不该把解释念出来，实际朗读：{spoken}"

    # 5. 「陪我语音聊会」之后：不用每条都说语音，也一直用语音；说「打字」才切回文字
    modes.clear()
    types = await run_case("陪我语音聊会吧", [Reply(text="好呀，我在听", emotion="笑", voice=False)])
    assert types == ["record"], f"开启语音聊天应发语音，实际：{types}"
    assert modes.get("private:20000") is True, "语音模式应被记住"
    types = await run_case("今天上班累吗", [Reply(text="还行吧，有点困", emotion="困", voice=False)])
    assert types == ["record"], f"语音模式下普通消息也应发语音，实际：{types}"
    types = await run_case("打字吧，我在公司", [Reply(text="好，那打字聊", emotion="笑", voice=False)])
    assert modes.get("private:20000") is False, "说打字应关闭语音模式"
    types = await run_case("今天吃啥了", [Reply(text="吃了碗面", emotion="吃饭", voice=False)])
    assert "text" in types and "record" not in types, f"关掉语音后应发文字，实际：{types}"

    print("simulate_voice passed")


if __name__ == "__main__":
    asyncio.run(main())
