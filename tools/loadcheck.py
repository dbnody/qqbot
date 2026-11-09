"""检查所有插件能否正常导入。运行：python tools/loadcheck.py"""

import sys
from pathlib import Path

import nonebot
from nonebot.adapters.onebot.v11 import Adapter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
loaded = nonebot.load_plugins("plugins")
print("loaded", len(loaded))
