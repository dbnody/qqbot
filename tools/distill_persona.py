"""从微信/QQ 聊天记录里蒸馏人格，生成 data/personas/<key>.json。

支持三种输入：
    1. 留痕 / WeChatMsg 导出的 CSV（列名含 IsSender、StrContent、Type 等）
    2. 整理过的 TXT（“名字：内容”或“2024-01-01 12:00:00 名字 + 换行内容”）
    3. JSON 数组（字段含 IsSender / StrContent 或 sender / content）

用法：
    python tools/distill_persona.py --file 聊天记录.csv --name 老王
    python tools/distill_persona.py --file 记录.txt --speaker 老王 --name 老王
    python tools/distill_persona.py --file 记录.csv --name 老王 --dry-run

注意：采样出来的消息会发给 DEEPSEEK_API_BASE_URL 指向的接口；想完全本地，
把它改成 Ollama 的 http://127.0.0.1:11434/v1 并把 DEEPSEEK_MODEL 换成对应模型。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

from app.ai_client import chat  # noqa: E402

PERSONA_DIR = ROOT / "data" / "personas"
NOISE = re.compile(r"\[(图片|表情|语音|视频|位置|动画表情|链接|红包|转账|文件|名片)\]|https?://\S+")
HEADER_TIME = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}[ T]\d{1,2}:\d{2}(:\d{2})?$")
PREFIX = re.compile(r"^(?P<who>[^:：\n]{1,24})[:：]\s*(?P<text>.+)$")

DISTILL_SYSTEM = """你是聊天人格建模师。用户会给某个人的真实聊天发言，你要提炼成可以直接给 AI 用的角色卡。

只从记录里能看出来的说话方式推断，不要编造记录中没有的具体隐私（住址、电话、身份证、账号、单位全称）。
不要把内容写成传记，重点是“怎么说话”，让 AI 照着这人的语气聊天。

输出严格 JSON（不要代码块、不要解释）：
{
  "name": "对方通常被怎么称呼",
  "tagline": "一句话人设，不超过 20 字",
  "voice": "音色名",
  "catchphrases": ["口头禅/高频词，最多 6 个"],
  "prompt": "250-400 字第二人称扮演指令"
}

voice 只能从这些里选一个最接近的：
zh-CN-XiaoxiaoNeural（女，活泼）、zh-CN-XiaoyiNeural（女，少女）、
zh-CN-YunxiNeural（男，少年）、zh-CN-YunjianNeural（男，成熟）、zh-CN-YunyangNeural（男，播音）。

prompt 里必须写到：句子长短与节奏、常用语气词和标点习惯、开心/吐槽/关心别人时分别怎么说话、
接话方式（会不会反问、会不会抢话）、以及“不要做的事”（比如不要突然变得文绉绉）。"""


def _clean(text: str) -> str:
    text = NOISE.sub("", str(text)).strip()
    text = re.sub(r"\s+", " ", text)
    return text if len(text) >= 2 else ""


def _rows(path: Path) -> list[dict]:
    """按常见编码读 CSV（导出工具有的写 GBK）。"""
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle))
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise SystemExit(f"读不出 {path.name} 的编码，试试另存为 UTF-8 CSV")


def read_csv(path: Path, speaker: str) -> list[str]:
    rows: list[str] = []
    for row in _rows(path):
        low = {str(k).strip().lower(): (v or "") for k, v in row.items()}
        msg_type = low.get("type", "")
        if msg_type and msg_type.strip() not in {"1", "49", ""}:
            continue  # 只要文字消息
        is_sender = low.get("issender", low.get("is_sender", ""))
        who = low.get("nickname", low.get("remark", low.get("talker", "")))
        if speaker:
            if speaker not in who and speaker not in low.get("displaycontent", ""):
                # 指定了说话人且列里没有，就退回按 IsSender 判断
                if is_sender.strip() != "0":
                    continue
        elif is_sender.strip() != "0":
            continue  # 默认取对方（IsSender=0）的发言
        content = low.get("strcontent", low.get("content", low.get("msg", low.get("text", ""))))
        cleaned = _clean(content)
        if cleaned:
            rows.append(cleaned)
    return rows


def read_txt(path: Path, speaker: str) -> list[str]:
    lines = path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    rows: list[str] = []
    current = ""
    for line in lines:
        raw = line.strip()
        if not raw:
            continue
        if HEADER_TIME.match(raw):
            current = ""
            continue
        match = PREFIX.match(raw)
        if match and len(match.group("who")) <= 12:
            who, text = match.group("who"), match.group("text")
            current = who
            if speaker and who != speaker:
                continue
            cleaned = _clean(text)
            if cleaned:
                rows.append(cleaned)
            continue
        if speaker and current and current != speaker:
            continue
        cleaned = _clean(raw)
        if cleaned:
            rows.append(cleaned)
    return rows


def read_json(path: Path, speaker: str) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[str] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        is_sender = str(item.get("IsSender", item.get("is_sender", item.get("sender", "0"))))
        who = str(item.get("talker", item.get("nickname", item.get("sender", ""))))
        if speaker:
            if speaker not in who and is_sender not in {"0", ""}:
                continue
        elif is_sender not in {"0", ""}:
            continue
        cleaned = _clean(item.get("StrContent") or item.get("content") or "")
        if cleaned:
            rows.append(cleaned)
    return rows


def sample(messages: list[str], limit: int) -> list[str]:
    if len(messages) <= limit:
        return messages
    step = len(messages) / limit
    return [messages[int(i * step)] for i in range(limit)]


def parse_json_payload(raw: str) -> dict:
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("模型没有返回 JSON")
    return json.loads(raw[start : end + 1])


async def distill(messages: list[str], name: str, voice: str) -> dict:
    body = "\n".join(f"- {message}" for message in messages)
    user_prompt = f"下面这个人的发言（共 {len(messages)} 条）：\n{body}\n\n请输出角色卡 JSON。"
    raw = await chat(
        [
            {"role": "system", "content": DISTILL_SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=1600,
        temperature=0.5,
    )
    data = parse_json_payload(raw)
    if name:
        data["name"] = name
    data.setdefault("name", name)
    if voice:
        data["voice"] = voice
    if not str(data.get("prompt") or "").strip():
        raise ValueError("模型没有给出 prompt")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="从聊天记录蒸馏人格")
    parser.add_argument("--file", required=True, help="CSV / TXT / JSON 聊天记录")
    parser.add_argument("--speaker", default="", help="要模仿的人（TXT 里必填，CSV 默认取 IsSender=0）")
    parser.add_argument("--name", default="", help="人格名字，默认用文件名")
    parser.add_argument("--key", default="", help="保存的文件名/切换用的 key，默认用名字")
    parser.add_argument("--voice", default="", help="强制指定 edge-tts 音色")
    parser.add_argument("--limit", type=int, default=300, help="最多采样多少条发言")
    parser.add_argument("--dry-run", action="store_true", help="只打印采样结果，不调用模型")
    args = parser.parse_args()

    path = Path(args.file).expanduser()
    if not path.is_file():
        sys.exit(f"找不到文件：{path}")
    suffix = path.suffix.lower()
    if suffix == ".csv":
        messages = read_csv(path, args.speaker)
    elif suffix == ".json":
        messages = read_json(path, args.speaker)
    else:
        messages = read_txt(path, args.speaker)

    messages = [message for message in messages if message]
    if len(messages) < 20:
        sys.exit(f"只解析到 {len(messages)} 条发言，太少了（至少 20 条），检查 --speaker 或导出格式")

    picked = sample(messages, args.limit)
    print(f"解析到 {len(messages)} 条，采样 {len(picked)} 条")
    if args.dry_run:
        for message in picked[:15]:
            print("  ", message)
        print("（--dry-run，未调用模型）")
        return

    persona = distill_sync(picked, args.name or path.stem, args.voice)
    key = re.sub(r'[\\/:*?"<>|\s]+', "_", args.key or persona["name"] or path.stem)
    PERSONA_DIR.mkdir(parents=True, exist_ok=True)
    target = PERSONA_DIR / f"{key}.json"
    persona.update({"source": path.name, "message_count": len(messages), "key": key})
    target.write_text(json.dumps(persona, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已生成：{target}")
    print(f"人设：{persona.get('tagline', '')}")
    print(f"口头禅：{'、'.join(persona.get('catchphrases') or [])}")
    print(f"\n重启 Bot 后可用：/人格 切换 {key}")
    print("（人格目录是每次读取的，Bot 正在运行也可以直接切）")


def distill_sync(messages: list[str], name: str, voice: str) -> dict:
    import asyncio

    return asyncio.run(distill(messages, name, voice))


if __name__ == "__main__":
    main()
