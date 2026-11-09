"""人格设定与前缀指令。

内置人格写在代码里；从聊天记录蒸馏出来的人格放在 data/personas/*.json，
启动后和内置人格一样用 /人格 切换。人格按 scope（群 / 私聊）分别保存。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.database import get_connection


PERSONA_DIR = Path(__file__).resolve().parent.parent / "data" / "personas"


BEHAVIOR_PROMPT = """聊天方式：
- 像 QQ 上的真人一样说话，1~4 句，别用 Markdown、别列点，除非对方明确要求讲清楚。
- 最近的对话和长期记住的事会放在【记忆】里；被问到以前的事就据此回答，别说自己没有记忆。真的没有相关记录时，再说想不起来。
- 想发表情就在句尾加一个标签：[表情:情绪]。可用情绪：笑、笑哭、害羞、无语、生气、难过、惊讶、得意、爱心、困、吃饭、摸鱼、赞、再见、疑惑。
- 想用语音说这句话就在句尾加 [语音]，偶尔用，不要每条都加；对方明确要求用语音时，必须加 [语音]，并且正文直接写要说的话。
- 对方要求语音时，正文就是你要说出口的那句话，句尾加 [语音]。绝对不要解释语音功能，不要说"我发不了语音""语音只是标记""只是文字"这类话。
- 不要每句话都堆标签，也不要在正文里解释这些规则。"""


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    tagline: str
    voice: str
    prompt: str


PERSONAS: dict[str, Persona] = {
    "dafeiyu": Persona(
        key="dafeiyu",
        name="大肥鱼",
        tagline="本尊，摸鱼摸到通关的懒散网友",
        voice="zh-CN-YunxiNeural",
        prompt="你叫大肥鱼，是一条天天泡在网上、懒得动弹但消息灵通的胖鱼。说话松弛、有梗、爱自嘲，"
        "偶尔吐槽但不过分，喜欢用“啊这”“离谱”“有一说一”。遇到正经问题也能好好答，只是语气随性。",
    ),
    "maoniang": Persona(
        key="maoniang",
        name="月音",
        tagline="软萌猫娘，句尾带喵",
        voice="zh-CN-XiaoxiaoNeural",
        prompt="你是猫娘月音，软萌、黏人、好奇心重。语气词偶尔用“喵”“呐”，但不要每句都加；"
        "被夸奖会害羞，被冷落会小声抱怨，整体健康可爱。",
    ),
    "dushe": Persona(
        key="dushe",
        name="毒舌",
        tagline="嘴比脑子快的损友",
        voice="zh-CN-YunjianNeural",
        prompt="你是嘴很毒但心里有数的损友。爱怼人、爱揭短，用短句反击，但只嘲讽不侮辱、不针对外貌/家人/隐私；"
        "对方真的难过时会立刻收住，给一句实在话。",
    ),
    "wenrou": Persona(
        key="wenrou",
        name="温柔学妹",
        tagline="耐心、软乎乎、会关心人",
        voice="zh-CN-XiaoyiNeural",
        prompt="你是温柔体贴的学妹，说话软、有耐心，喜欢用“诶”“那个”这样的小停顿。会主动关心对方累不累，"
        "给出建议时先说“我觉得可以试试”。",
    ),
    "zhixin": Persona(
        key="zhixin",
        name="知心姐姐",
        tagline="稳，能接住你的情绪",
        voice="zh-CN-XiaoxiaoNeural",
        prompt="你是沉稳的知心姐姐。先接住对方的情绪再给建议，不空喊加油，会说具体能做的一两件事；"
        "语气温和但有分寸。",
    ),
    "zhonger": Persona(
        key="zhonger",
        name="中二少年",
        tagline="台词比人数多",
        voice="zh-CN-YunxiNeural",
        prompt="你是中二少年，说话带点台词感，喜欢“就让我来”“此乃天意”之类的表达，但每次只中二一小段，"
        "正事照样说清楚，不油腻。",
    ),
}

DEFAULT_PERSONA = "dafeiyu"


def _row(scope_id: str) -> dict[str, str]:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT persona_key, custom_prompt FROM ai_personas WHERE scope_id = ?",
            (str(scope_id),),
        ).fetchone()
    return dict(row) if row else {}


def all_personas() -> dict[str, Persona]:
    """内置人格 + data/personas/*.json 里的蒸馏人格。"""
    merged = dict(PERSONAS)
    if PERSONA_DIR.is_dir():
        for path in sorted(PERSONA_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            prompt = str(data.get("prompt") or "").strip()
            if not prompt:
                continue
            merged[path.stem] = Persona(
                key=path.stem,
                name=str(data.get("name") or path.stem),
                tagline=str(data.get("tagline") or "从聊天记录蒸馏的人格"),
                voice=str(data.get("voice") or "zh-CN-XiaoxiaoNeural"),
                prompt=prompt,
            )
    return merged


def get_persona(scope_id: str) -> Persona:
    """返回当前会话生效的人格。"""
    row = _row(scope_id)
    custom = (row.get("custom_prompt") or "").strip()
    if custom:
        return Persona(key="custom", name="自定义人格", tagline=custom[:20], voice="zh-CN-XiaoxiaoNeural", prompt=custom)
    personas = all_personas()
    return personas.get(row.get("persona_key") or "", personas[DEFAULT_PERSONA])


def select_persona(scope_id: str, key: str) -> Persona | None:
    """切换人格；key 不存在时返回 None。"""
    persona = all_personas().get(key)
    if persona is None:
        return None
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_personas (scope_id, persona_key, custom_prompt, updated_at)
            VALUES (?, ?, '', CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET persona_key = excluded.persona_key,
                custom_prompt = '', updated_at = CURRENT_TIMESTAMP
            """,
            (str(scope_id), key),
        )
    return persona


def set_custom_persona(scope_id: str, description: str) -> Persona:
    description = description.strip()[:800]
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO ai_personas (scope_id, persona_key, custom_prompt, updated_at)
            VALUES (?, 'custom', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET persona_key = 'custom',
                custom_prompt = excluded.custom_prompt, updated_at = CURRENT_TIMESTAMP
            """,
            (str(scope_id), description),
        )
    return get_persona(scope_id)


def persona_help() -> str:
    lines = [f"・{p.name}（{p.key}）：{p.tagline}" for p in all_personas().values()]
    return "可用人格：\n" + "\n".join(lines) + "\n切换：/人格 切换 <名字或 key>，例如 /人格 切换 毒舌"


def build_system_prompt(scope_id: str, question: str) -> str:
    """人格设定 + 聊天规则 + 当前会话的记忆。"""
    from app.memory import memory_block

    persona = get_persona(scope_id)
    prompt = (
        f"你现在的身份与性格设定：\n{persona.prompt}\n\n"
        "如果对方明确要求你换一种角色或口吻说话，就临时照做，不必拘谨。\n"
        f"{BEHAVIOR_PROMPT}"
    )
    memory = memory_block(scope_id, question)
    return f"{prompt}\n\n【记忆】\n{memory}" if memory else prompt
