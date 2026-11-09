"""人格、记忆、语音、表情的调试与管理命令。"""

from __future__ import annotations

from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageEvent, MessageSegment
from nonebot.params import CommandArg

from app import stickers
from app.sticker_fetch import sync
from app.memory import memory_overview
from app.persona import all_personas, get_persona, persona_help, select_persona, set_custom_persona
from app.tts import synthesize


def _scope(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):
        return f"group:{event.group_id}"
    return f"private:{event.user_id}"


def _match_persona(text: str):
    text = text.strip().lower()
    if not text:
        return None
    personas = all_personas()
    for key, persona in personas.items():
        if text in {key.lower(), persona.name.lower()}:
            return persona
    for persona in personas.values():
        if text and (text in persona.name.lower() or text in persona.tagline.lower()):
            return persona
    return None


persona_command = on_command("人格", aliases={"角色", "切换人格"}, priority=5, block=True)


@persona_command.handle()
async def handle_persona(event: MessageEvent, args=CommandArg()) -> None:
    text = args.extract_plain_text().strip()
    scope = _scope(event)
    current = get_persona(scope)

    if not text or text in {"列表", "list"}:
        await persona_command.finish(
            f"当前人格：{current.name}（{current.tagline}）\n\n{persona_help()}\n自定义：/人格 自定义 <一句话设定>"
        )

    if text.startswith(("自定义", "custom")):
        description = text[3:].strip(" ：:") if text.startswith("自定义") else text[6:].strip(" ：:")
        if len(description) < 4:
            await persona_command.finish("用法：/人格 自定义 一个爱讲冷笑话的东北大叔")
        persona = set_custom_persona(scope, description)
        await persona_command.finish(f"好，从现在起我演这个角色：{persona.prompt[:60]}……")

    keyword = text.removeprefix("切换").strip(" ：:")
    persona = _match_persona(keyword)
    if persona is None:
        await persona_command.finish(f"没找到「{keyword}」这个角色。\n{persona_help()}")
    select_persona(scope, persona.key)
    await persona_command.finish(f"人格已切换为「{persona.name}」：{persona.tagline}")


memory_command = on_command("记忆", aliases={"查看记忆", "记忆状态"}, priority=5, block=True)


@memory_command.handle()
async def handle_memory(event: MessageEvent) -> None:
    await memory_command.finish(memory_overview(_scope(event)))


voice_command = on_command("语音", aliases={"说"}, priority=5, block=True)


@voice_command.handle()
async def handle_voice(event: MessageEvent, args=CommandArg()) -> None:
    text = args.extract_plain_text().strip()
    if not text:
        await voice_command.finish("用法：/语音 要读出来的那句话")
    audio = await synthesize(text, get_persona(_scope(event)).voice)
    if audio is None:
        await voice_command.finish("语音合成失败了，检查一下 edge-tts 安装或网络。")
    await voice_command.finish(Message(MessageSegment.record(Path(audio).resolve().as_uri())))


sticker_command = on_command("表情", priority=5, block=True)


@sticker_command.handle()
async def handle_sticker(args=CommandArg()) -> None:
    emotion = args.extract_plain_text().strip()
    if not emotion:
        packs = stickers.packs()
        if not packs:
            await sticker_command.finish(
                "还没有图片表情素材。把图片按情绪放进 data/stickers/<情绪>/ 即可，"
                "例如 data/stickers/笑/1.gif。"
            )
        detail = "、".join(f"{name}({count})" for name, count in packs.items())
        await sticker_command.finish(f"素材：{detail}\n发送：/表情 笑")
    path = stickers.pick(emotion)
    if path is None:
        await sticker_command.finish(f"没有「{emotion}」的图片素材。")
    await sticker_command.finish(Message(MessageSegment.image(path.resolve().as_uri())))


find_sticker_command = on_command("找表情", aliases={"同步表情", "补表情"}, priority=5, block=True)


@find_sticker_command.handle()
async def handle_find_sticker(args=CommandArg()) -> None:
    force = args.extract_plain_text().strip() in {"强制", "全部", "重下"}
    if force:
        await find_sticker_command.send("重新下载整套大肥鱼表情…")
    else:
        await find_sticker_command.send("检查并补齐大肥鱼表情包…")
    added = await sync(force=force)
    total = sum(added.values())
    if not added:
        await find_sticker_command.finish("没有需要补的，或者网络不通。")
    detail = "、".join(f"{name}+{count}" for name, count in added.items())
    await find_sticker_command.finish(f"同步完成：新增 {total} 张（{detail}）")
