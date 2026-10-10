"""/ping：用于验证 Bot 是否正常工作。"""

from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent


ping_command = on_command("ping", aliases={"测试"}, priority=10, block=True)


@ping_command.handle()
async def handle_ping(event: MessageEvent) -> None:
    """收到 /ping 后返回健康状态。"""
    await ping_command.finish("pong！QQ Bot 正常运行。")
