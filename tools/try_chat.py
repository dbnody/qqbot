"""手动联调：不经过 QQ，直接跑一轮完整对话（DeepSeek + 人格 + 记忆 + 表情 + 语音）。

用法：
    python tools/try_chat.py 你好呀
    python tools/try_chat.py 你好呀 --persona 毒舌
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from app import stickers  # noqa: E402
from app.ai_client import chat_reply, is_configured  # noqa: E402
from app.database import init_database  # noqa: E402
from app.memory import append_ai_memory, load_ai_memory  # noqa: E402
from app.persona import all_personas, build_system_prompt, get_persona, select_persona  # noqa: E402
from app.tts import synthesize  # noqa: E402

SCOPE = "private:try_chat"


def _persona_key(text: str) -> str:
    personas = all_personas()
    if text in personas:
        return text
    for persona in personas.values():
        if text in {persona.name, persona.key}:
            return persona.key
    return ""


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="?", default="你好呀，介绍一下你自己")
    parser.add_argument("--persona", default="")
    args = parser.parse_args()

    if not is_configured():
        sys.exit("DEEPSEEK_API_KEY 未配置")
    init_database()
    if args.persona:
        key = _persona_key(args.persona)
        if not key:
            sys.exit(f"没有「{args.persona}」这个人格")
        select_persona(SCOPE, key)
    persona = get_persona(SCOPE)

    history = load_ai_memory(SCOPE)
    prompt = build_system_prompt(SCOPE, args.question)
    print(f"人格：{persona.name}｜历史消息：{len(history)} 条")
    print("问：", args.question)

    reply = await chat_reply(prompt, history, args.question, "阿明")
    print("答：", reply.text)
    print("表情标签：", reply.emotion or "（无）", "→", stickers.pick(reply.emotion) if reply.emotion else "（无素材）")
    print("语音标签：", reply.voice)
    if reply.voice:
        audio = await synthesize(reply.text, persona.voice)
        print("语音文件：", audio)

    append_ai_memory(SCOPE, "user", f"阿明：{args.question}")
    append_ai_memory(SCOPE, "assistant", reply.text)


if __name__ == "__main__":
    asyncio.run(main())
