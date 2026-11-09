"""离线自检：不联网、不需要 NoneBot 启动。

运行：python tools/selfcheck.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP_DB = Path(tempfile.gettempdir()) / "qqbot_selfcheck.db"
TMP_DB.unlink(missing_ok=True)
os.environ["QQBOT_DATABASE_PATH"] = str(TMP_DB)
os.environ.pop("DEEPSEEK_API_KEY", None)

from app.ai_client import _endpoint, parse_reply  # noqa: E402
from app.database import init_database  # noqa: E402
from app.memory import add_fact, append_ai_memory, load_ai_memory, recall_facts  # noqa: E402
from app.persona import get_persona, select_persona, set_custom_persona  # noqa: E402
from app.stickers import face, normalize  # noqa: E402


def check_parse() -> None:
    reply = parse_reply("今天也在摸鱼[表情:笑哭][语音]")
    assert reply.text == "今天也在摸鱼", reply.text
    assert reply.emotion == "笑哭"
    assert reply.voice is True
    plain = parse_reply("【表情：可爱】好耶")
    assert plain.emotion == "可爱" and plain.text == "好耶", plain
    assert parse_reply("没有标签").voice is False


def check_stickers() -> None:
    assert normalize("开心") == "笑"
    assert normalize("哭") == "难过"
    assert normalize("完全不认识的情绪") == ""
    assert face("白眼") == "22"


def check_memory() -> None:
    init_database()
    scope = "group:1"
    append_ai_memory(scope, "user", "我叫阿明，喜欢打游戏")
    append_ai_memory(scope, "assistant", "记住了")
    assert load_ai_memory(scope)[0]["content"].startswith("我叫阿明")
    add_fact(scope, "用户叫阿明")
    add_fact(scope, "用户喜欢打游戏")
    add_fact(scope, "用户住在杭州")
    hits = recall_facts(scope, "阿明喜欢什么")
    assert "用户叫阿明" in hits[:2], hits
    assert "用户喜欢打游戏" in hits[:2], hits
    assert all("杭州" not in hit for hit in hits)


def check_persona() -> None:
    scope = "private:2"
    assert get_persona(scope).key == "dafeiyu"
    assert select_persona(scope, "dushe") is not None
    assert get_persona(scope).name == "毒舌"
    set_custom_persona(scope, "一个爱讲冷笑话的东北大叔")
    assert get_persona(scope).key == "custom"


def check_endpoint() -> None:
    assert _endpoint("https://api.deepseek.com") == "https://api.deepseek.com/v1/chat/completions"
    assert _endpoint("https://api.openai.com/v1") == "https://api.openai.com/v1/chat/completions"


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("check_"):
            func()
            print(f"ok  {name}")
    try:
        TMP_DB.unlink(missing_ok=True)
    except OSError:
        pass  # Windows 上句柄可能还没释放，临时目录会自己清
    print("selfcheck passed")
