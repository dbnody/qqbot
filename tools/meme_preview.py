"""把十种梗图都画一遍，方便看效果。运行：python tools/meme_preview.py [输出目录]"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=True)

import nonebot  # noqa: E402
from nonebot.adapters.onebot.v11 import Adapter  # noqa: E402

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)

plugin = importlib.import_module("plugins.meme")

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "meme_preview"
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    ("crying_cat", "今天也要努力上班"),
    ("perfect", "这波操作完美"),
    ("masterpiece", "这就是艺术"),
    ("pornhub", "周末的快乐"),
    ("sign", "求求你别卷了"),
    ("panda", "我熊猫听不懂"),
    ("doge", "这合理吗"),
    ("shocked", "真的假的"),
    ("rainbow", "彩虹屁给你安排上"),
    ("classic", "今日份梗图请查收"),
]


def main() -> None:
    for template, text in CASES:
        path = plugin._make_image(template, text)
        target = OUT / f"{template}.png"
        target.write_bytes(path.read_bytes())
        path.unlink(missing_ok=True)
        print(f"{target}  {target.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
