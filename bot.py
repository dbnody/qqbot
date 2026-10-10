"""QQ Bot 程序入口。

启动顺序：
1. 初始化 NoneBot 驱动；
2. 注册 OneBot V11 适配器；
3. 加载 plugins/ 下的插件；
4. 初始化 SQLite 数据库；
5. 启动本地服务，等待 QQ 适配器通过 WebSocket 连接。
"""

from pathlib import Path

from dotenv import load_dotenv
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from app.database import init_database


def main() -> None:
    """初始化并启动 Bot。"""
    # NoneBot 不一定会自动读取项目根目录 .env，显式加载自定义配置。
    # 以项目 .env 为准，避免任务计划程序或系统环境中的空变量覆盖配置。
    load_dotenv(Path(__file__).with_name(".env"), override=True)
    nonebot.init()
    driver = nonebot.get_driver()
    driver.register_adapter(OneBotV11Adapter)

    # 显式加载 plugins 目录，避免插件位置依赖当前工作目录以外的配置。
    nonebot.load_plugins("plugins")
    init_database()

    nonebot.run()


if __name__ == "__main__":
    main()
