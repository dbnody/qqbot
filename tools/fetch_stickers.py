"""只同步大肥鱼（鲸鱼娘）表情包到 data/stickers/<情绪>/，不会拉别的图。

用法：
    python tools/fetch_stickers.py          # 缺什么补什么
    python tools/fetch_stickers.py --force  # 全部重下

素材来源：https://github.com/diwer/ai-biaoqingbao（非商业二创）
下载完用 /表情 查看各情绪素材数量，或直接 /表情 笑 发一张。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=True)
sys.path.insert(0, str(ROOT))

from app import sticker_fetch, stickers  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="同步大肥鱼表情包")
    parser.add_argument("--force", action="store_true", help="全部重下")
    args = parser.parse_args()

    added = asyncio.run(sticker_fetch.sync(force=args.force))
    print(f"素材目录：{stickers.sticker_root()}")
    if added:
        detail = "、".join(f"{name}+{count}" for name, count in added.items())
        print(f"新增 {sum(added.values())} 张：{detail}")
    else:
        print("没有需要补的，或者网络不通")
    print("各情绪：" + "、".join(f"{name}({count})" for name, count in stickers.packs().items()))


if __name__ == "__main__":
    main()
