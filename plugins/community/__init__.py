"""群聊统计、词云和互动小游戏。"""

from __future__ import annotations

import re
import random

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg

from app.community import (
    DRAW_ROUNDS,
    IDIOM_ROUNDS,
    IDIOMS,
    RIDDLE_ROUNDS,
    SONG_ROUNDS,
    _nickname,
    clear_game_rounds,
    group_statistics,
    new_idiom_round,
    new_riddle,
    new_song_round,
    normalize_answer,
    record_group_message,
    render_word_cloud,
    speaking_ranking,
)


def _group_only(event: GroupMessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent)


def _days(args: str, default: int = 7) -> int:
    match = re.search(r"\d+", args)
    return max(1, min(int(match.group()) if match else default, 365))


message_recorder = on_message(priority=0, block=False)


@message_recorder.handle()
async def handle_message_recorder(event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    record_group_message(event.group_id, event.user_id, _nickname(event), event.get_plaintext())


statistics_command = on_command("群统计", aliases={"消息统计", "统计"}, priority=10, block=True)


@statistics_command.handle()
async def handle_statistics(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await statistics_command.finish("群统计功能只能在群聊中使用。")
    days = _days(args.extract_plain_text(), 1)
    result = group_statistics(str(event.group_id), days)
    await statistics_command.finish(
        f"本群最近 {days} 天消息统计：\n消息数量：{result['messages']} 条\n活跃成员：{result['users']} 人"
    )


ranking_command = on_command("发言排行", aliases={"排行榜", "发言榜"}, priority=10, block=True)


@ranking_command.handle()
async def handle_ranking(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await ranking_command.finish("发言排行榜只能在群聊中使用。")
    days = _days(args.extract_plain_text(), 7)
    rows = speaking_ranking(str(event.group_id), days)
    if not rows:
        await ranking_command.finish(f"最近 {days} 天暂时没有统计到群消息。")
    lines = [f"本群最近 {days} 天发言排行榜："]
    for index, row in enumerate(rows, 1):
        lines.append(f"{index}. {row['nickname'] or row['user_id']}：{row['count']} 条")
    await ranking_command.finish("\n".join(lines))


wordcloud_command = on_command("词云", aliases={"群词云", "wordcloud"}, priority=10, block=True)


@wordcloud_command.handle()
async def handle_wordcloud(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await wordcloud_command.finish("词云功能只能在群聊中使用。")
    days = _days(args.extract_plain_text(), 7)
    path = render_word_cloud(str(event.group_id), days)
    if path is None:
        await wordcloud_command.finish(f"最近 {days} 天还没有足够的文字消息，暂时无法生成词云。")
    try:
        await wordcloud_command.finish(
            Message([MessageSegment.text(f"本群最近 {days} 天的词云："), MessageSegment.image(file=str(path.resolve()))])
        )
    finally:
        path.unlink(missing_ok=True)


riddle_command = on_command("猜谜", aliases={"猜谜语", "谜语"}, priority=10, block=True)


@riddle_command.handle()
async def handle_riddle(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await riddle_command.finish("猜谜功能只能在群聊中使用。")
    action = args.extract_plain_text().strip()
    group_id = str(event.group_id)
    if action in {"结束", "停止", "end"}:
        RIDDLE_ROUNDS.pop(group_id, None)
        await riddle_command.finish("本轮猜谜已结束。")
    if action in {"提示", "给提示", "hint"} and (round_ := RIDDLE_ROUNDS.get(group_id)):
        await riddle_command.finish(f"提示：{round_.hint}")
    clear_game_rounds(group_id, "riddle")
    round_ = new_riddle(group_id)
    await riddle_command.finish(f"猜谜开始！\n{round_.question}\n发送 /猜谜 提示 可查看提示。")


idiom_command = on_command("成语接龙", aliases={"接龙", "idiom"}, priority=10, block=True)


@idiom_command.handle()
async def handle_idiom(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await idiom_command.finish("成语接龙只能在群聊中使用。")
    action = args.extract_plain_text().strip()
    group_id = str(event.group_id)
    if action in {"结束", "停止", "end"}:
        IDIOM_ROUNDS.pop(group_id, None)
        await idiom_command.finish("成语接龙已结束。")
    clear_game_rounds(group_id, "idiom")
    start = new_idiom_round(group_id)
    await idiom_command.finish(f"成语接龙开始！\n第一个成语：{start}\n下一位请接“{start[-1]}”开头的成语。")


draw_command = on_command("你画我猜", aliases={"画猜", "draw"}, priority=10, block=True)


@draw_command.handle()
async def handle_draw(bot: Bot, event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await draw_command.finish("你画我猜只能在群聊中使用。")
    group_id = str(event.group_id)
    if args.extract_plain_text().strip() in {"结束", "停止", "end"}:
        DRAW_ROUNDS.pop(group_id, None)
        await draw_command.finish("你画我猜已结束。")
    clear_game_rounds(group_id, "draw")
    answer, hint = random.choice(
        (("长城", "一个著名的中国建筑"), ("大熊猫", "黑白相间的国宝"), ("飞机", "可以在天空飞行"), ("蛋糕", "生日时常见的甜点"), ("吉他", "一种常见的弦乐器"))
    )
    DRAW_ROUNDS[group_id] = {"answer": answer, "drawer": str(event.user_id), "has_image": False}
    try:
        await bot.send_private_msg(user_id=event.user_id, message=f"你是本轮画手，答案是：{answer}\n提示：{hint}\n请在群里发送一张图片，让大家猜。")
        private_hint = "画手答案已通过私聊发送。"
    except Exception:
        private_hint = "暂时无法发送私聊，请画手确认已开启临时会话。"
    await draw_command.finish(f"你画我猜开始！{private_hint}\n画手请发送图片，其他成员直接发送答案。")


song_command = on_command("猜歌名", aliases={"猜歌", "听歌猜名", "song"}, priority=10, block=True)


@song_command.handle()
async def handle_song(event: GroupMessageEvent, args=CommandArg()) -> None:
    if not _group_only(event):
        await song_command.finish("猜歌名只能在群聊中使用。")
    group_id = str(event.group_id)
    action = args.extract_plain_text().strip()
    if action in {"结束", "停止", "end"}:
        SONG_ROUNDS.pop(group_id, None)
        await song_command.finish("猜歌名已结束。")
    if action in {"提示", "给提示", "hint"} and (song := SONG_ROUNDS.get(group_id)):
        await song_command.finish(f"歌手提示：{song[1]}")
    clear_game_rounds(group_id, "song")
    title, singer, hint = new_song_round(group_id)
    await song_command.finish(f"猜歌名开始！\n歌词提示：{hint}\n发送歌名作答，发送 /猜歌名 提示 查看歌手提示。")


game_messages = on_message(priority=20, block=False)


@game_messages.handle()
async def handle_game_messages(event: GroupMessageEvent) -> None:
    if not isinstance(event, GroupMessageEvent):
        return
    group_id = str(event.group_id)
    text = event.get_plaintext().strip()
    if not text or text.startswith(("/", "！", "!")):
        # 你画我猜允许画手发送图片，图片消息通常没有 plaintext。
        draw = DRAW_ROUNDS.get(group_id)
        if draw and any(segment.type == "image" for segment in event.get_message()):
            draw["has_image"] = True
            await game_messages.send("画作已收到！大家开始猜吧，直接发送你认为的答案。")
        return

    riddle = RIDDLE_ROUNDS.get(group_id)
    if riddle:
        if text in {"提示", "给提示"}:
            await game_messages.send(f"提示：{riddle.hint}")
        elif normalize_answer(text) == normalize_answer(riddle.answer):
            RIDDLE_ROUNDS.pop(group_id, None)
            await game_messages.send(f"回答正确！答案是“{riddle.answer}”，下一轮发送 /猜谜。")
        return

    current = IDIOM_ROUNDS.get(group_id)
    if current and len(text) >= 4:
        if text not in IDIOMS:
            await game_messages.send("这个成语不在本轮词库中，请换一个常见成语。")
        elif text[0] != current[-1]:
            await game_messages.send(f"接龙失败，应使用“{current[-1]}”开头的成语。")
        else:
            IDIOM_ROUNDS[group_id] = text
            await game_messages.send(f"{text}，接得好！下一位请接“{text[-1]}”开头的成语。")
        return

    song = SONG_ROUNDS.get(group_id)
    if song:
        title, singer, hint = song
        if text in {"提示", "给提示"}:
            await game_messages.send(f"歌手提示：{singer}")
        elif normalize_answer(text) == normalize_answer(title):
            SONG_ROUNDS.pop(group_id, None)
            await game_messages.send(f"猜对了！答案是《{title}》——{singer}。下一轮发送 /猜歌名。")
        else:
            await game_messages.send("还没猜对，再想想看～")
        return

    draw = DRAW_ROUNDS.get(group_id)
    if draw and draw.get("has_image") and normalize_answer(text) == normalize_answer(str(draw["answer"])):
        DRAW_ROUNDS.pop(group_id, None)
        await game_messages.send(f"猜对了！答案是“{text}”，本轮你画我猜结束。")
