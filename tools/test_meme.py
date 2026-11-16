"""回归检查：十种梗图都能画出来，尺寸对、画面不空、模板名都能对上。

运行：python tools/test_meme.py [输出目录]
"""

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

from PIL import Image  # noqa: E402

plugin = importlib.import_module("plugins.meme")

EXPECTED = {
    "crying_cat",
    "perfect",
    "masterpiece",
    "pornhub",
    "sign",
    "panda",
    "doge",
    "shocked",
    "classic",
    "rainbow",
}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)

    names = set(plugin._TEMPLATES.values())
    assert names == EXPECTED, f"模板名对不上：多 {names - EXPECTED}，少 {EXPECTED - names}"

    for name in sorted(EXPECTED):
        path = plugin._make_image(name, "这是一句测试用的梗图文字")
        try:
            image = Image.open(path)
            image.load()
            assert image.size == (900, 650), f"{name} 尺寸不对：{image.size}"
            colors = len(image.convert("RGB").getcolors(maxcolors=1 << 20) or [])
            assert colors > 200, f"{name} 画面太空，只有 {colors} 种颜色"
            if out is not None:
                (out / f"{name}.png").write_bytes(path.read_bytes())
        finally:
            path.unlink(missing_ok=True)

    long_text = "一二三四五六七八九十一二三四五六七八九十"
    assert plugin._wrap_text(long_text, 10).count("\n") == 1, "长文本应折成两行"
    assert plugin._wrap_text("短句子") == "短句子", "短文本不该换行"

    print("test_meme passed")


if __name__ == "__main__":
    main()
