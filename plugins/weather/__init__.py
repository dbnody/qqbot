"""天气查询：使用 wttr.in 公共接口，不需要 API Key。"""

from urllib.parse import quote

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg


weather_command = on_command("天气", aliases={"weather"}, priority=10, block=True)


@weather_command.handle()
async def handle_weather(event: MessageEvent, args=CommandArg()) -> None:
    city = args.extract_plain_text().strip()
    if not city:
        await weather_command.finish("用法：/天气 城市，例如：/天气 上海")

    url = f"https://wttr.in/{quote(city)}"
    try:
        async with httpx.AsyncClient(
            timeout=8.0,
            headers={"User-Agent": "qqbot-python/1.0"},
        ) as client:
            response = await client.get(url, params={"format": "j1"})
            response.raise_for_status()
            payload = response.json()
        current = payload["current_condition"][0]
        description = current["weatherDesc"][0]["value"]
        await weather_command.finish(
            f"{city} 当前天气：{description}\n"
            f"温度：{current['temp_C']}℃，体感：{current['FeelsLikeC']}℃\n"
            f"湿度：{current['humidity']}%，风速：{current['windspeedKmph']} km/h"
        )
    except (httpx.HTTPError, KeyError, IndexError, ValueError):
        await weather_command.finish("天气服务暂时不可用，请稍后再试或检查城市名称。")
