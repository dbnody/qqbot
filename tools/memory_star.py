"""命令行生成记忆星图。

用法：
    python tools/memory_star.py                 # 出 PNG
    python tools/memory_star.py --gif           # 圆环 → 连线 → 满天星 的 GIF
    python tools/memory_star.py --scope group:123 --out data/starmap/group.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import starmap  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="把记忆库画成星图")
    parser.add_argument("--scope", default="", help="只画某个会话，例如 group:123456")
    parser.add_argument("--out", default="", help="输出路径，默认 data/starmap/memory_star.png")
    parser.add_argument("--gif", action="store_true", help="额外生成阶段动画 GIF")
    args = parser.parse_args()

    path = starmap.render(args.out or None, gif=args.gif, scope=args.scope)
    if path is None:
        print("没有可画的记忆：ai_facts 还是空的，先聊几轮让它攒事实。")
        return
    print(f"已生成：{path}")
    if args.gif:
        print(f"过程动画：{path.with_suffix('.gif')}")

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    main()
