"""回归检查：音色样本能存能删，克隆请求带对参考音频和文字，失败能回落。

用一个本地假服务器顶替硅基流动的 /audio/speech 和 /audio/transcriptions，
不联网、不花钱。

运行：python tools/test_voice_profile.py
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

TMP = Path(tempfile.mkdtemp(prefix="voice-test-"))
os.environ["QQBOT_DATABASE_PATH"] = str(TMP / "test.db")
os.environ["TTS_ENABLED"] = "true"
os.environ["TTS_ENGINE"] = "edge"
os.environ["VOICE_CLONE_URL"] = ""
os.environ["SILICONFLOW_API_KEY"] = "test-key"

FAKE_AUDIO = b"ID3" + b"\0" * 6000
TRANSCRIPT = "大家好，我是测试声音"
CALLS: list[tuple[str, dict]] = []
STATE = {"fail_speech": False}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # 静音
        pass

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path.endswith("/audio/transcriptions"):
            CALLS.append(("asr", {"size": len(body)}))
            payload = json.dumps({"text": TRANSCRIPT}, ensure_ascii=False).encode()
            self._reply(200, "application/json", payload)
            return
        if self.path.endswith("/audio/speech"):
            payload = json.loads(body)
            CALLS.append(("speech", payload))
            if STATE["fail_speech"]:
                self._reply(500, "application/json", b'{"message":"boom"}')
                return
            self._reply(200, "audio/mpeg", FAKE_AUDIO)
            return
        self._reply(404, "text/plain", b"nope")

    def _reply(self, code: int, ctype: str, payload: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ["SILICONFLOW_API_BASE"] = f"http://127.0.0.1:{server.server_port}/v1"

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
tts.tts_dir = lambda: (TMP / "tts").resolve().mkdir(parents=True, exist_ok=True) or (TMP / "tts")
SCOPE = "private:50001"
SAMPLE = b"RIFF" + b"\0" * 8000  # 够长就行，测试不看内容


class FakeArgs:
    def __init__(self, text: str = "") -> None:
        self.text = text

    def extract_plain_text(self) -> str:
        return self.text


def make_wav(name: str = "sample.wav") -> Path:
    path = TMP / name
    path.write_bytes(SAMPLE)
    return path


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
            for segment in item:
                parts.append(f"<{segment.type}>")
        elif isinstance(item, MessageSegment):
            parts.append(f"<{item.type}>")
        else:
            parts.append(str(item))
    return " ".join(parts)


def check_profile() -> None:
    assert voice_profile.get_profile(SCOPE) is None, "一开始不该有样本"
    path = voice_profile.save_sample(SCOPE, SAMPLE, ".wav", "测试原话")
    assert path.exists() and path.read_bytes() == SAMPLE, "样本应原样落盘"
    profile = voice_profile.get_profile(SCOPE)
    assert profile is not None and profile["ref_path"] == str(path)
    assert profile["prompt_text"] == "测试原话"
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


def check_provider() -> None:
    assert clone_tts.provider() == "siliconflow", clone_tts.provider()
    assert clone_tts.enabled() is True
    assert "硅基流动" in clone_tts.status()


def check_clone_request() -> None:
    voice_profile.save_sample(SCOPE, SAMPLE, ".wav", "这句话就是参考音频里的原话")
    CALLS.clear()
    audio = asyncio.run(tts.synthesize("你好呀，这是克隆出来的声音", None, SCOPE))
    assert audio is not None and audio.exists(), "应该合成出音频"
    assert audio.read_bytes() == FAKE_AUDIO, "应原样写入服务返回的音频"

    speech = [payload for kind, payload in CALLS if kind == "speech"]
    assert len(speech) == 1, f"应该只请求一次，实际 {len(speech)}"
    payload = speech[0]
    assert payload["model"].endswith("CosyVoice2-0.5B"), payload["model"]
    assert payload["references"][0]["text"] == "这句话就是参考音频里的原话", "参考文字要一起发过去"
    prefix = "data:audio/wav;base64,"
    assert payload["references"][0]["audio"].startswith(prefix), "参考音频要用 base64 data URI"
    raw = base64.b64decode(payload["references"][0]["audio"][len(prefix):])
    assert len(raw) > 1024, "参考音频不能是空的"
    assert payload["stream"] is False, "非流式才方便一次写盘"

    CALLS.clear()
    again = asyncio.run(tts.synthesize("你好呀，这是克隆出来的声音", None, SCOPE))
    assert again == audio, "第二次应该命中缓存"
    assert not [kind for kind, _ in CALLS if kind == "speech"], "缓存命中不该再请求"


def check_fallback() -> None:
    voice_profile.save_sample(SCOPE, SAMPLE, ".wav", "原话")
    STATE["fail_speech"] = True
    originality = tts._edge_tts

    async def fake_edge(text, voice, target):
        Path(target).write_bytes(SAMPLE)
        return True

    tts._edge_tts = fake_edge
    try:
        got = asyncio.run(tts.synthesize("克隆挂了也别哑", None, SCOPE))
        assert got is not None and got.exists(), "克隆失败应回落到 edge-tts"
    finally:
        tts._edge_tts = originality
        STATE["fail_speech"] = False
    voice_profile.clear(SCOPE)


def check_transcribe() -> None:
    CALLS.clear()
    text = asyncio.run(clone_tts.transcribe(SAMPLE, "sample.wav"))
    assert text == TRANSCRIPT, text
    assert [kind for kind, _ in CALLS] == ["asr"], "应该走转录接口"


def check_plugin() -> None:
    voice_profile.clear(SCOPE)
    wav = make_wav()
    record = MessageSegment.record(file=wav.resolve().as_uri())

    reply = run(group_event(), "录入 原话")
    assert "私聊" in reply, f"群里应被拦住，实际：{reply}"

    reply = run(private_event(Message("x")), "状态")
    assert "还没录过" in reply, f"状态应显示未录入，实际：{reply}"

    CALLS.clear()
    reply = run(private_event(Message(record)), "录入 这是我自己说的原话")
    assert "存好了" in reply and "<record>" in reply, f"录入后应回到试听语音，实际：{reply}"
    profile = voice_profile.get_profile(SCOPE)
    assert profile is not None and profile["prompt_text"] == "这是我自己说的原话", profile
    assert not [kind for kind, _ in CALLS if kind == "asr"], "自己带了原话就不该再调 ASR"

    reply = run(private_event(Message("x")), "录入")
    assert "没找到语音" in reply, f"没有语音应提示，实际：{reply}"

    voice_profile.clear(SCOPE)
    CALLS.clear()
    reply = run(private_event(Message(record)), "录入")
    assert "参考文字" in reply and "存好了" in reply, f"没带原话应自动识别，实际：{reply}"
    profile = voice_profile.get_profile(SCOPE)
    assert profile is not None and profile["prompt_text"] == TRANSCRIPT, profile
    assert [kind for kind, _ in CALLS].count("asr") == 1, "应该自动调一次 ASR"

    reply = run(private_event(Message("x")), "试听 你好呀")
    assert "<record>" in reply, f"试听应发语音，实际：{reply}"

    reply = run(private_event(Message("x")), "文本 改过的原话")
    assert "改好了" in reply, f"改文字应成功，实际：{reply}"
    assert voice_profile.get_profile(SCOPE)["prompt_text"] == "改过的原话"

    reply = run(private_event(Message("x")), "状态")
    assert "已经录过" in reply and "改过的原话" in reply, f"状态应显示参考文字，实际：{reply}"

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
    check_provider()
    check_profile()
    check_clone_request()
    check_transcribe()
    check_fallback()
    check_plugin()
    check_hidden_from_help()
    server.shutdown()
    print("test_voice_profile passed")


if __name__ == "__main__":
    main()
